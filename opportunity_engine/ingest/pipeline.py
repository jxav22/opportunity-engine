"""Normalisation, dedupe keys, and per-source ingest orchestration."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from typing import Any

from opportunity_engine import db
from opportunity_engine.ingest.base import IngestContext, RawItem
from opportunity_engine.ingest.registry import get_adapter

logger = logging.getLogger(__name__)

_REMOTE_HINTS = re.compile(
    r"\b(remote|work from home|wfh|anywhere|distributed)\b",
    re.IGNORECASE,
)


def _norm_text(value: str | None) -> str:
    if not value:
        return ""
    s = value.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def make_dedupe_key(item: RawItem) -> str:
    """Prefer stable external_id; fall back to title+company+location."""
    if item.external_id:
        return f"ext:{_norm_text(item.external_id)}"
    return (
        "ttl:"
        + _norm_text(item.title)
        + "|"
        + _norm_text(item.company_name)
        + "|"
        + _norm_text(item.location)
    )


def infer_remote_ok(item: RawItem) -> int | None:
    blob = " ".join(
        x for x in [item.location or "", item.title or "", (item.description or "")[:500]] if x
    )
    if not blob:
        return None
    if _REMOTE_HINTS.search(blob):
        return 1
    # Ashby workplaceType often in raw
    workplace = None
    if isinstance(item.raw, dict):
        workplace = item.raw.get("workplaceType") or item.raw.get("isRemote")
    if workplace is True or (isinstance(workplace, str) and workplace.lower() in {"remote", "hybrid"}):
        return 1 if str(workplace).lower() != "hybrid" else 1
    if workplace is False:
        return 0
    return None


def normalize_raw_item(
    item: RawItem,
    *,
    source_id: str,
    source_url: str,
) -> dict[str, Any]:
    company_name = (item.company_name or "Unknown").strip() or "Unknown"
    title = item.title.strip()
    return {
        "dedupe_key": make_dedupe_key(item),
        "category": item.category or "employment",
        "title": title,
        "company_name": company_name,
        "location": item.location.strip() if item.location else None,
        "remote_ok": infer_remote_ok(item),
        "url": item.url,
        "description": item.description,
        "source_id": source_id,
        "source_url": source_url or item.url,
        "posted_at": item.posted_at,
        "raw": item.raw,
        "is_demo": 0,
    }


def ingest_source(
    conn: sqlite3.Connection,
    source_row: sqlite3.Row | dict[str, Any],
    ctx: IngestContext | None = None,
) -> dict[str, Any]:
    """Fetch one source, upsert opportunities, record ingest_run + health."""
    source_id = source_row["id"]
    adapter_name = source_row["adapter"]
    config = source_row["config_json"]
    if isinstance(config, str):
        config = json.loads(config)

    own_ctx = ctx is None
    ctx = ctx or IngestContext()
    run_id = db.start_ingest_run(conn, source_id)
    conn.commit()

    items_seen = 0
    items_new = 0
    status = "ok"
    error: str | None = None
    source_url = (
        config.get("url")
        or config.get("feed_url")
        or config.get("board_token")
        or config.get("site")
        or config.get("board")
        or source_id
    )
    if adapter_name == "greenhouse" and config.get("board_token"):
        source_url = f"https://boards-api.greenhouse.io/v1/boards/{config['board_token']}/jobs"
    elif adapter_name == "lever" and config.get("site"):
        source_url = f"https://api.lever.co/v0/postings/{config['site']}"
    elif adapter_name == "ashby" and config.get("board"):
        source_url = f"https://api.ashbyhq.com/posting-api/job-board/{config['board']}"

    try:
        adapter = get_adapter(adapter_name)
        raw_items = adapter.fetch(config, ctx)
        items_seen = len(raw_items)
        for raw in raw_items:
            norm = normalize_raw_item(raw, source_id=source_id, source_url=str(source_url))
            company_id = db.ensure_company(conn, norm["company_name"], data_quality="partial")
            _, is_new = db.upsert_opportunity(
                conn,
                dedupe_key=norm["dedupe_key"],
                category=norm["category"],
                title=norm["title"],
                company_name=norm["company_name"],
                company_id=company_id,
                location=norm["location"],
                remote_ok=norm["remote_ok"],
                url=norm["url"],
                description=norm["description"],
                source_id=norm["source_id"],
                source_url=norm["source_url"],
                posted_at=norm["posted_at"],
                raw=norm["raw"],
                is_demo=0,
            )
            if is_new:
                items_new += 1
        conn.commit()
    except Exception as exc:  # noqa: BLE001 — record and continue other sources
        logger.exception("Ingest failed for %s", source_id)
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
        conn.rollback()
        # reopen transaction for finish_ingest_run
        try:
            db.finish_ingest_run(
                conn,
                run_id,
                source_id,
                status=status,
                items_seen=items_seen,
                items_new=items_new,
                error=error,
            )
            conn.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record error run for %s", source_id)
            conn.rollback()
    else:
        db.finish_ingest_run(
            conn,
            run_id,
            source_id,
            status=status,
            items_seen=items_seen,
            items_new=items_new,
            error=error,
        )
        conn.commit()
    finally:
        if own_ctx:
            ctx.close()

    return {
        "source_id": source_id,
        "run_id": run_id,
        "status": status,
        "items_seen": items_seen,
        "items_new": items_new,
        "error": error,
    }
