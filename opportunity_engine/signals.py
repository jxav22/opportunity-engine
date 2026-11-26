"""Event-based early-warning signals (quality over volume)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_STRENGTH_THRESHOLD = 0.55

SIGNAL_KINDS = (
    "first_eng_vacancy",
    "funding",
    "nz_hiring",
    "accelerator_open",
    "relevant_event",
)

FUNDING_RE = re.compile(
    r"\b(raised|raises|funding|series [a-d]|seed round|venture)\b", re.I
)
NZ_HIRE_RE = re.compile(
    r"\b(new zealand|auckland|wellington|christchurch|\bnz\b)\b", re.I
)
ACCEL_RE = re.compile(
    r"\b(accelerator|YC\b|y combinator|techstars|startup school|applications? open)\b",
    re.I,
)
EVENT_RE = re.compile(
    r"\b(meetup|conference|hackathon|summit|workshop|office hours)\b", re.I
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def signal_id(kind: str, dedupe_key: str) -> str:
    raw = f"{kind}::{dedupe_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _existing_keys(conn: sqlite3.Connection) -> set[str]:
    keys: set[str] = set()
    try:
        for row in conn.execute("SELECT id, kind, title, company_id FROM signals"):
            keys.add(row[0])
            # Also track soft dedupe fingerprint
            keys.add(f"{row[1]}::{row[3] or ''}::{(row[2] or '')[:80]}")
    except sqlite3.Error:
        pass
    return keys


def _upsert_signal(
    conn: sqlite3.Connection,
    *,
    kind: str,
    title: str,
    summary: str,
    strength: float,
    company_id: str | None = None,
    opportunity_id: str | None = None,
    evidence: list[str] | None = None,
    dedupe_key: str | None = None,
    existing: set[str] | None = None,
) -> dict[str, Any] | None:
    dedupe_key = dedupe_key or f"{company_id or ''}::{title}"
    sid = signal_id(kind, dedupe_key)
    fingerprint = f"{kind}::{company_id or ''}::{title[:80]}"
    if existing is not None and (sid in existing or fingerprint in existing):
        return None
    payload = {
        "id": sid,
        "kind": kind,
        "title": title,
        "summary": summary,
        "company_id": company_id,
        "opportunity_id": opportunity_id,
        "strength": round(float(strength), 2),
        "created_at": _now_iso(),
        "acknowledged": 0,
        "evidence_json": json.dumps(evidence or [], ensure_ascii=False),
    }
    conn.execute(
        """
        INSERT INTO signals (
            id, kind, title, summary, company_id, opportunity_id,
            strength, created_at, acknowledged, evidence_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (
            payload["id"],
            payload["kind"],
            payload["title"],
            payload["summary"],
            payload["company_id"],
            payload["opportunity_id"],
            payload["strength"],
            payload["created_at"],
            payload["acknowledged"],
            payload["evidence_json"],
        ),
    )
    if existing is not None:
        existing.add(sid)
        existing.add(fingerprint)
    return payload


def detect_first_eng_vacancy(
    conn: sqlite3.Connection,
    *,
    months: int = 3,
    existing: set[str] | None = None,
) -> list[dict[str, Any]]:
    """First engineering vacancy for a company in N months."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months)
    cutoff_s = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    created: list[dict[str, Any]] = []
    rows = conn.execute(
        """
        SELECT company_id, company_name, id, title, discovered_at
        FROM opportunities
        WHERE category = 'employment'
          AND company_id IS NOT NULL
          AND (title LIKE '%Engineer%' OR title LIKE '%Developer%'
               OR title LIKE '%SWE%' OR description LIKE '%software engineer%')
        ORDER BY discovered_at ASC
        """
    ).fetchall()
    by_company: dict[str, list] = {}
    for company_id, company_name, oid, title, discovered_at in rows:
        by_company.setdefault(company_id, []).append(
            (company_name, oid, title, discovered_at)
        )
    for company_id, items in by_company.items():
        recent = [
            it
            for it in items
            if (it[3] or "") >= cutoff_s
        ]
        older = [
            it
            for it in items
            if (it[3] or "") < cutoff_s
        ]
        if recent and not older:
            company_name, oid, title, discovered_at = recent[0]
            sig = _upsert_signal(
                conn,
                kind="first_eng_vacancy",
                title=f"First eng vacancy in {months} months: {company_name}",
                summary=f"{title} — first engineering-style role observed recently.",
                strength=0.75,
                company_id=company_id,
                opportunity_id=oid,
                evidence=[f"opportunity_id={oid}", f"discovered_at={discovered_at}"],
                dedupe_key=f"{company_id}:first_eng:{months}m",
                existing=existing,
            )
            if sig:
                created.append(sig)
    return created


def detect_funding_signals(
    conn: sqlite3.Connection,
    *,
    existing: set[str] | None = None,
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    try:
        rows = conn.execute(
            """
            SELECT id, company_id, title, summary, url, observed_at
            FROM company_developments
            WHERE kind = 'funding'
            """
        ).fetchall()
    except sqlite3.Error:
        rows = []
    for did, company_id, title, summary, url, observed_at in rows:
        sig = _upsert_signal(
            conn,
            kind="funding",
            title=title or "Funding development",
            summary=(summary or "")[:300],
            strength=0.7,
            company_id=company_id,
            evidence=[e for e in [url, observed_at, f"development_id={did}"] if e],
            dedupe_key=f"funding:{did}",
            existing=existing,
        )
        if sig:
            created.append(sig)

    # Also scan opportunities/descriptions lightly
    for row in conn.execute(
        "SELECT id, company_id, title, description FROM opportunities"
    ):
        oid, company_id, title, description = row
        blob = f"{title or ''}\n{description or ''}"
        if FUNDING_RE.search(blob):
            m = FUNDING_RE.search(blob)
            sig = _upsert_signal(
                conn,
                kind="funding",
                title=f"Funding language in opportunity: {title}",
                summary="Posting or linked text mentions funding activity.",
                strength=0.58,
                company_id=company_id,
                opportunity_id=oid,
                evidence=[m.group(0) if m else "funding"],
                dedupe_key=f"funding-opp:{oid}",
                existing=existing,
            )
            if sig:
                created.append(sig)
    return created


def detect_nz_hiring(
    conn: sqlite3.Connection,
    *,
    existing: set[str] | None = None,
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT id, company_id, company_name, title, location, description, remote_ok
        FROM opportunities
        WHERE category = 'employment' AND stale = 0
        """
    ):
        oid, company_id, company_name, title, location, description, remote_ok = row
        blob = f"{title}\n{location or ''}\n{description or ''}"
        if not NZ_HIRE_RE.search(blob) and not NZ_HIRE_RE.search(location or ""):
            continue
        strength = 0.8 if NZ_HIRE_RE.search(location or "") else 0.65
        if remote_ok in (1, True):
            strength = min(1.0, strength + 0.05)
        sig = _upsert_signal(
            conn,
            kind="nz_hiring",
            title=f"NZ-relevant hiring: {company_name or company_id or 'unknown'}",
            summary=f"{title} ({location or 'location n/a'})",
            strength=strength,
            company_id=company_id,
            opportunity_id=oid,
            evidence=[e for e in [location, title] if e],
            dedupe_key=f"nz:{oid}",
            existing=existing,
        )
        if sig:
            created.append(sig)
    return created


def detect_accelerator_open(
    conn: sqlite3.Connection,
    *,
    existing: set[str] | None = None,
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for row in conn.execute(
        "SELECT id, company_id, title, description, category FROM opportunities"
    ):
        oid, company_id, title, description, category = row
        blob = f"{title or ''}\n{description or ''}"
        if not ACCEL_RE.search(blob) and category != "entrepreneurial":
            continue
        if not ACCEL_RE.search(blob):
            continue
        m = ACCEL_RE.search(blob)
        sig = _upsert_signal(
            conn,
            kind="accelerator_open",
            title=f"Accelerator / cohort cue: {title}",
            summary="Accelerator or applications-open language detected.",
            strength=0.72,
            company_id=company_id,
            opportunity_id=oid,
            evidence=[m.group(0) if m else "accelerator"],
            dedupe_key=f"accel:{oid}",
            existing=existing,
        )
        if sig:
            created.append(sig)
    return created


def detect_relevant_events(
    conn: sqlite3.Connection,
    profile: dict[str, Any] | None = None,
    *,
    existing: set[str] | None = None,
) -> list[dict[str, Any]]:
    interests = [str(i).lower() for i in ((profile or {}).get("interests") or [])]
    created: list[dict[str, Any]] = []
    for row in conn.execute(
        "SELECT id, company_id, title, description, category FROM opportunities"
    ):
        oid, company_id, title, description, category = row
        blob = f"{title or ''}\n{description or ''}"
        if category != "community" and not EVENT_RE.search(blob):
            continue
        if not EVENT_RE.search(blob) and category != "community":
            continue
        strength = 0.6
        evidence = _match_list(EVENT_RE, blob)
        for interest in interests:
            token = interest.split()[0]
            if token and token in blob.lower():
                strength = min(1.0, strength + 0.1)
                evidence.append(f"interest:{interest}")
        if strength < 0.6:
            continue
        sig = _upsert_signal(
            conn,
            kind="relevant_event",
            title=f"Event / community: {title}",
            summary="Community or event opportunity matching profile interests.",
            strength=strength,
            company_id=company_id,
            opportunity_id=oid,
            evidence=evidence,
            dedupe_key=f"event:{oid}",
            existing=existing,
        )
        if sig:
            created.append(sig)
    return created


def _match_list(pattern: re.Pattern[str], text: str) -> list[str]:
    out: list[str] = []
    for m in pattern.finditer(text):
        g = m.group(0)
        if g not in out:
            out.append(g)
        if len(out) >= 5:
            break
    return out


def refresh_signals(
    conn: sqlite3.Connection,
    profile: dict[str, Any] | None = None,
    *,
    strength_threshold: float = DEFAULT_STRENGTH_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    Detect and upsert signals; dedupe vs prior rows.
    Configurable strength threshold — prefer quality over volume.
    """
    existing = _existing_keys(conn)
    created: list[dict[str, Any]] = []
    created.extend(detect_first_eng_vacancy(conn, existing=existing))
    created.extend(detect_funding_signals(conn, existing=existing))
    created.extend(detect_nz_hiring(conn, existing=existing))
    created.extend(detect_accelerator_open(conn, existing=existing))
    created.extend(detect_relevant_events(conn, profile, existing=existing))

    # Drop weak new signals (delete just-inserted below threshold).
    kept: list[dict[str, Any]] = []
    for sig in created:
        if float(sig["strength"]) < strength_threshold:
            conn.execute("DELETE FROM signals WHERE id = ?", (sig["id"],))
            continue
        kept.append(sig)
    return kept


def list_signals(
    conn: sqlite3.Connection,
    *,
    strength_threshold: float = DEFAULT_STRENGTH_THRESHOLD,
    include_acknowledged: bool = False,
) -> list[dict[str, Any]]:
    sql = """
        SELECT id, kind, title, summary, company_id, opportunity_id,
               strength, created_at, acknowledged, evidence_json
        FROM signals
        WHERE strength >= ?
    """
    params: list[Any] = [strength_threshold]
    if not include_acknowledged:
        sql += " AND acknowledged = 0"
    sql += " ORDER BY strength DESC, created_at DESC"
    out: list[dict[str, Any]] = []
    for row in conn.execute(sql, params):
        out.append(
            {
                "id": row[0],
                "kind": row[1],
                "title": row[2],
                "summary": row[3],
                "company_id": row[4],
                "opportunity_id": row[5],
                "strength": row[6],
                "created_at": row[7],
                "acknowledged": row[8],
                "evidence": json.loads(row[9] or "[]"),
            }
        )
    return out
