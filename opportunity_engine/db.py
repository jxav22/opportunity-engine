"""SQLite schema + upsert helpers matching shared contracts.

Bootstrap aligned with Agent A's ingest helpers. Agent B may replace
this module — keep schema column names and helper signatures stable.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "opportunity_engine.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data_json TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    adapter TEXT NOT NULL,
    config_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_success_at TEXT,
    last_error TEXT,
    last_attempt_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    website TEXT,
    location TEXT,
    industry TEXT,
    product_description TEXT,
    engineering_stack_json TEXT,
    company_size TEXT,
    funding_stage TEXT,
    remote_policy TEXT,
    accessibility_notes TEXT,
    why_interesting TEXT,
    source_links_json TEXT,
    last_verified_at TEXT,
    interest_level INTEGER NOT NULL DEFAULT 0,
    monitoring_status TEXT NOT NULL DEFAULT 'watching',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data_quality TEXT NOT NULL DEFAULT 'partial'
);

CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    company_id TEXT,
    company_name TEXT NOT NULL,
    location TEXT,
    remote_ok INTEGER,
    url TEXT NOT NULL,
    description TEXT,
    source_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    posted_at TEXT,
    last_seen_at TEXT NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0,
    is_demo INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT,
    skills_json TEXT,
    score_total REAL,
    score_breakdown_json TEXT,
    accessibility_score REAL,
    quality_score REAL,
    next_action TEXT,
    action_rationale TEXT,
    uncertainties_json TEXT,
    why_valuable TEXT,
    why_relevant TEXT,
    evidence_summary TEXT,
    saved INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new'
);

CREATE TABLE IF NOT EXISTS company_developments (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    observed_at TEXT NOT NULL,
    is_hiring_evidence INTEGER NOT NULL DEFAULT 0,
    source_id TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    company_id TEXT,
    opportunity_id TEXT,
    strength REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    evidence_json TEXT
);

CREATE TABLE IF NOT EXISTS skill_mentions (
    id TEXT PRIMARY KEY,
    skill TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    company_id TEXT,
    mentioned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    items_seen INTEGER NOT NULL DEFAULT 0,
    items_new INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_opportunities_source ON opportunities(source_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_company ON opportunities(company_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_stale ON opportunities(stale);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "unknown"


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(
    conn: sqlite3.Connection | None = None,
    db_path: Path | str | None = None,
) -> sqlite3.Connection:
    """Initialize schema. Accepts existing conn (Agent A style) or db_path."""
    owns = conn is None
    if conn is None:
        conn = connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def ensure_company(
    conn: sqlite3.Connection,
    name: str,
    *,
    website: str | None = None,
    data_quality: str = "partial",
) -> str:
    """Upsert company by slugified name; return company id."""
    company_id = slugify(name)
    now = utc_now()
    row = conn.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE companies SET name = ?, updated_at = ? WHERE id = ?",
            (name, now, company_id),
        )
        return company_id
    conn.execute(
        """
        INSERT INTO companies (
            id, name, website, interest_level, monitoring_status,
            created_at, updated_at, data_quality
        ) VALUES (?, ?, ?, 0, 'watching', ?, ?, ?)
        """,
        (company_id, name, website, now, now, data_quality),
    )
    return company_id


def upsert_opportunity(
    conn: sqlite3.Connection,
    *,
    dedupe_key: str,
    category: str,
    title: str,
    company_name: str,
    company_id: str | None,
    location: str | None,
    remote_ok: int | None,
    url: str,
    description: str | None,
    source_id: str,
    source_url: str,
    posted_at: str | None,
    raw: dict[str, Any] | None,
    is_demo: int = 0,
) -> tuple[str, bool]:
    """Insert or refresh an opportunity. Returns (id, is_new)."""
    now = utc_now()
    existing = conn.execute(
        "SELECT id, discovered_at FROM opportunities WHERE dedupe_key = ?",
        (dedupe_key,),
    ).fetchone()
    raw_json = json.dumps(raw, ensure_ascii=False, default=str) if raw is not None else None
    if existing:
        conn.execute(
            """
            UPDATE opportunities SET
                title = ?,
                company_id = COALESCE(?, company_id),
                company_name = ?,
                location = ?,
                remote_ok = ?,
                url = ?,
                description = COALESCE(?, description),
                source_id = ?,
                source_url = ?,
                posted_at = COALESCE(?, posted_at),
                last_seen_at = ?,
                stale = 0,
                is_demo = ?,
                raw_json = COALESCE(?, raw_json)
            WHERE dedupe_key = ?
            """,
            (
                title,
                company_id,
                company_name,
                location,
                remote_ok,
                url,
                description,
                source_id,
                source_url,
                posted_at,
                now,
                is_demo,
                raw_json,
                dedupe_key,
            ),
        )
        return existing["id"], False

    opp_id = uuid.uuid5(uuid.NAMESPACE_URL, dedupe_key).hex
    conn.execute(
        """
        INSERT INTO opportunities (
            id, dedupe_key, category, title, company_id, company_name,
            location, remote_ok, url, description, source_id, source_url,
            discovered_at, posted_at, last_seen_at, stale, is_demo, raw_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'new')
        """,
        (
            opp_id,
            dedupe_key,
            category,
            title,
            company_id,
            company_name,
            location,
            remote_ok,
            url,
            description,
            source_id,
            source_url,
            now,
            posted_at,
            now,
            is_demo,
            raw_json,
        ),
    )
    return opp_id, True


def upsert_source(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    name: str,
    adapter: str,
    config: dict[str, Any],
    enabled: int = 1,
) -> None:
    now = utc_now()
    existing = conn.execute("SELECT id FROM sources WHERE id = ?", (source_id,)).fetchone()
    config_json = json.dumps(config, ensure_ascii=False)
    if existing:
        conn.execute(
            """
            UPDATE sources SET name = ?, adapter = ?, config_json = ?, enabled = ?
            WHERE id = ?
            """,
            (name, adapter, config_json, enabled, source_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO sources (id, name, adapter, config_json, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (source_id, name, adapter, config_json, enabled, now),
        )


def list_enabled_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM sources WHERE enabled = 1 ORDER BY id"
        ).fetchall()
    )


def start_ingest_run(conn: sqlite3.Connection, source_id: str) -> str:
    run_id = uuid.uuid4().hex
    started = utc_now()
    conn.execute(
        """
        INSERT INTO ingest_runs (id, source_id, started_at, status, items_seen, items_new)
        VALUES (?, ?, ?, 'ok', 0, 0)
        """,
        (run_id, source_id, started),
    )
    conn.execute(
        "UPDATE sources SET last_attempt_at = ? WHERE id = ?",
        (started, source_id),
    )
    return run_id


def finish_ingest_run(
    conn: sqlite3.Connection,
    run_id: str,
    source_id: str,
    *,
    status: str,
    items_seen: int,
    items_new: int,
    error: str | None = None,
) -> None:
    finished = utc_now()
    conn.execute(
        """
        UPDATE ingest_runs
        SET finished_at = ?, status = ?, items_seen = ?, items_new = ?, error = ?
        WHERE id = ?
        """,
        (finished, status, items_seen, items_new, error, run_id),
    )
    if status == "ok":
        conn.execute(
            """
            UPDATE sources SET last_success_at = ?, last_error = NULL WHERE id = ?
            """,
            (finished, source_id),
        )
    elif status == "partial":
        conn.execute(
            """
            UPDATE sources SET last_success_at = ?, last_error = ? WHERE id = ?
            """,
            (finished, error, source_id),
        )
    else:
        conn.execute(
            "UPDATE sources SET last_error = ? WHERE id = ?",
            (error, source_id),
        )
