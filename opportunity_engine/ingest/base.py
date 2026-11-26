"""SourceAdapter protocol, RawItem, and SSRF-safe HTTP fetch helpers."""

from __future__ import annotations

import ipaddress
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from opportunity_engine.models import RawItem

logger = logging.getLogger(__name__)

# Re-export for adapters that import from base
__all__ = ["RawItem", "IngestContext", "SourceAdapter", "safe_get", "SafeFetchError"]


class SafeFetchError(Exception):
    """Raised when a URL fails SSRF checks or fetch policy."""


@dataclass
class IngestContext:
    """Shared fetch / rate-limit context for adapters."""

    timeout: float = 20.0
    min_interval_seconds: float = 0.4
    user_agent: str = "OpportunityEngine/0.1 (+local ingest; respectful)"
    _last_fetch_at: float = field(default=0.0, repr=False)
    _client: httpx.Client | None = field(default=None, repr=False)

    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=False,
                headers={"User-Agent": self.user_agent},
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> IngestContext:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class SourceAdapter(Protocol):
    name: str

    def fetch(self, config: dict, ctx: IngestContext) -> list[RawItem]: ...


_BLOCKED_HOSTS = {
    "metadata.google.internal",
    "metadata.google",
    "metadata",
    "localhost",
}


def _host_is_blocked(hostname: str) -> bool:
    host = hostname.strip(".").lower()
    if not host:
        return True
    if host in _BLOCKED_HOSTS or host.endswith(".localhost") or host.endswith(".local"):
        return True
    # Literal IP in hostname
    try:
        ip = ipaddress.ip_address(host)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        return False


def _resolved_ips_are_public(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SafeFetchError(f"DNS resolution failed for {hostname}: {exc}") from exc
    if not infos:
        raise SafeFetchError(f"No addresses for {hostname}")
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise SafeFetchError(f"Blocked non-public IP {ip} for host {hostname}")


def validate_fetch_url(url: str) -> str:
    """Allow only http/https to public hosts. Returns normalized URL."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SafeFetchError(f"Disallowed scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise SafeFetchError("URL missing hostname")
    if parsed.username or parsed.password:
        raise SafeFetchError("URLs with credentials are not allowed")
    if _host_is_blocked(parsed.hostname):
        raise SafeFetchError(f"Blocked host: {parsed.hostname}")
    _resolved_ips_are_public(parsed.hostname)
    return url


def safe_get(
    ctx: IngestContext,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_bytes: int = 5_000_000,
) -> httpx.Response:
    """SSRF-safe GET with politeness delay, timeouts, and size cap."""
    validate_fetch_url(url)
    elapsed = time.monotonic() - ctx._last_fetch_at
    if elapsed < ctx.min_interval_seconds:
        time.sleep(ctx.min_interval_seconds - elapsed)
    client = ctx.client()
    resp = client.get(url, params=params, headers=headers)
    ctx._last_fetch_at = time.monotonic()
    # Re-validate redirect Location targets if client ever follows; we disable redirects.
    if resp.status_code in {301, 302, 303, 307, 308}:
        location = resp.headers.get("location")
        if not location:
            raise SafeFetchError(f"Redirect without Location from {url}")
        # Absolute or relative — resolve then validate
        next_url = str(resp.url.join(location))
        validate_fetch_url(next_url)
        elapsed = time.monotonic() - ctx._last_fetch_at
        if elapsed < ctx.min_interval_seconds:
            time.sleep(ctx.min_interval_seconds - elapsed)
        resp = client.get(next_url, params=params, headers=headers)
        ctx._last_fetch_at = time.monotonic()
        if resp.status_code in {301, 302, 303, 307, 308}:
            raise SafeFetchError("Refusing multi-hop redirects")
    content_length = resp.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise SafeFetchError(f"Response too large: {content_length} bytes")
    if len(resp.content) > max_bytes:
        raise SafeFetchError(f"Response body exceeds {max_bytes} bytes")
    return resp
