"""SQLite schema + upsert helpers matching shared contracts.

Canonical persistence (Agent B). Keeps Agent A ingest + Agent C ranking helper signatures.
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
CREATE INDEX IF NOT EXISTS idx_opportunities_demo ON opportunities(is_demo);
CREATE INDEX IF NOT EXISTS idx_opportunities_saved ON opportunities(saved);
CREATE INDEX IF NOT EXISTS idx_opportunities_category ON opportunities(category);
CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(monitoring_status);
CREATE INDEX IF NOT EXISTS idx_skill_mentions_skill ON skill_mentions(skill);
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
        "SELECT id, discovered_at, raw_json FROM opportunities WHERE dedupe_key = ?",
        (dedupe_key,),
    ).fetchone()
    # Merge provenance across sources when the same dedupe_key is seen again.
    if existing and raw is not None:
        try:
            prev = json.loads(existing["raw_json"]) if existing["raw_json"] else {}
        except (TypeError, json.JSONDecodeError, KeyError):
            prev = {"_previous_raw": existing["raw_json"] if "raw_json" in existing.keys() else None}
        sources = prev.get("_sources") if isinstance(prev, dict) else None
        if not isinstance(sources, list):
            sources = [{"seen_at": utc_now(), "payload": prev}] if prev else []
        sources.append({"seen_at": utc_now(), "payload": raw, "source_id": source_id})
        raw_json = json.dumps(
            {"latest": raw, "_sources": sources[-20:], "merged_at": utc_now()},
            ensure_ascii=False,
            default=str,
        )
    else:
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

# --- Agent B company / watchlist / query helpers (signatures additive) ---

def upsert_company(
    conn: sqlite3.Connection,
    *,
    id: str | None = None,
    name: str,
    website: str | None = None,
    location: str | None = None,
    industry: str | None = None,
    product_description: str | None = None,
    engineering_stack_json: str | list | None = None,
    company_size: str | None = None,
    funding_stage: str | None = None,
    remote_policy: str | None = None,
    accessibility_notes: str | None = None,
    why_interesting: str | None = None,
    source_links_json: str | list | dict | None = None,
    last_verified_at: str | None = None,
    interest_level: int = 0,
    monitoring_status: str = "watching",
    notes: str | None = None,
    data_quality: str = "partial",
) -> str:
    """Full company upsert. Unknown facts stay NULL — never fabricate."""
    company_id = id or slugify(name)
    now = utc_now()
    if isinstance(engineering_stack_json, (list, dict)):
        engineering_stack_json = json.dumps(engineering_stack_json)
    if isinstance(source_links_json, (list, dict)):
        source_links_json = json.dumps(source_links_json)

    existing = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if existing:
        def keep(new, old_key):
            return new if new is not None else existing[old_key]
        conn.execute(
            """
            UPDATE companies SET
                name=?, website=?, location=?, industry=?, product_description=?,
                engineering_stack_json=?, company_size=?, funding_stage=?, remote_policy=?,
                accessibility_notes=?, why_interesting=?, source_links_json=?,
                last_verified_at=?, interest_level=?, monitoring_status=?, notes=?,
                data_quality=?, updated_at=?
            WHERE id=?
            """,
            (
                name,
                keep(website, "website"),
                keep(location, "location"),
                keep(industry, "industry"),
                keep(product_description, "product_description"),
                keep(engineering_stack_json, "engineering_stack_json"),
                keep(company_size, "company_size"),
                keep(funding_stage, "funding_stage"),
                keep(remote_policy, "remote_policy"),
                keep(accessibility_notes, "accessibility_notes"),
                keep(why_interesting, "why_interesting"),
                keep(source_links_json, "source_links_json"),
                keep(last_verified_at, "last_verified_at"),
                interest_level,
                monitoring_status,
                keep(notes, "notes"),
                data_quality,
                now,
                company_id,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO companies (
                id, name, website, location, industry, product_description,
                engineering_stack_json, company_size, funding_stage, remote_policy,
                accessibility_notes, why_interesting, source_links_json,
                last_verified_at, interest_level, monitoring_status, notes,
                created_at, updated_at, data_quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id, name, website, location, industry, product_description,
                engineering_stack_json, company_size, funding_stage, remote_policy,
                accessibility_notes, why_interesting, source_links_json,
                last_verified_at, interest_level, monitoring_status, notes,
                now, now, data_quality,
            ),
        )
    return company_id


def update_company_notes(
    conn: sqlite3.Connection,
    company_id: str,
    *,
    notes: str | None = None,
    interest_level: int | None = None,
    monitoring_status: str | None = None,
) -> bool:
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not row:
        return False
    conn.execute(
        """
        UPDATE companies SET notes=?, interest_level=?, monitoring_status=?, updated_at=?
        WHERE id=?
        """,
        (
            notes if notes is not None else row["notes"],
            interest_level if interest_level is not None else row["interest_level"],
            monitoring_status if monitoring_status is not None else row["monitoring_status"],
            utc_now(),
            company_id,
        ),
    )
    return True


def get_watchlist(
    conn: sqlite3.Connection,
    *,
    status: str | None = "watching",
) -> list[sqlite3.Row]:
    if status:
        return list(
            conn.execute(
                """
                SELECT * FROM companies WHERE monitoring_status = ?
                ORDER BY interest_level DESC, name COLLATE NOCASE
                """,
                (status,),
            ).fetchall()
        )
    return list(
        conn.execute(
            "SELECT * FROM companies ORDER BY interest_level DESC, name COLLATE NOCASE"
        ).fetchall()
    )


def mark_stale(
    conn: sqlite3.Connection,
    *,
    older_than_days: int = 14,
    source_id: str | None = None,
    exclude_demo: bool = True,
) -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - older_than_days * 86400
    cutoff_iso = (
        datetime.fromtimestamp(cutoff, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    sql = "UPDATE opportunities SET stale = 1 WHERE last_seen_at < ? AND stale = 0"
    params: list[Any] = [cutoff_iso]
    if exclude_demo:
        sql += " AND is_demo = 0"
    if source_id:
        sql += " AND source_id = ?"
        params.append(source_id)
    return conn.execute(sql, params).rowcount


def list_opportunities(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    saved: int | None = None,
    stale: int | None = None,
    is_demo: int | None = None,
    min_score: float | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if category:
        clauses.append("category = ?"); params.append(category)
    if saved is not None:
        clauses.append("saved = ?"); params.append(saved)
    if stale is not None:
        clauses.append("stale = ?"); params.append(stale)
    if is_demo is not None:
        clauses.append("is_demo = ?"); params.append(is_demo)
    if min_score is not None:
        clauses.append("score_total >= ?"); params.append(min_score)
    if status:
        clauses.append("status = ?"); params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    return list(
        conn.execute(
            f"""
            SELECT * FROM opportunities
            {where}
            ORDER BY COALESCE(score_total, -1) DESC, last_seen_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    )


def rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]

