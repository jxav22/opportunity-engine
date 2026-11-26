"""SSRF and fetch policy tests."""

from __future__ import annotations

import pytest

from opportunity_engine.ingest.base import SafeFetchError, validate_fetch_url


def test_blocks_file_scheme():
    with pytest.raises(SafeFetchError):
        validate_fetch_url("file:///etc/passwd")


def test_blocks_localhost():
    with pytest.raises(SafeFetchError):
        validate_fetch_url("http://localhost/secret")


def test_blocks_metadata_host():
    with pytest.raises(SafeFetchError):
        validate_fetch_url("http://metadata.google.internal/computeMetadata/v1/")


def test_blocks_private_ip_literal():
    with pytest.raises(SafeFetchError):
        validate_fetch_url("http://127.0.0.1/")
    with pytest.raises(SafeFetchError):
        validate_fetch_url("http://10.0.0.5/x")
    with pytest.raises(SafeFetchError):
        validate_fetch_url("http://192.168.1.1/")


def test_allows_https_public_host():
    url = validate_fetch_url("https://boards-api.greenhouse.io/v1/boards/discord/jobs")
    assert url.startswith("https://")
