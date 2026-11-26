#!/usr/bin/env python3
"""Run enabled source adapters once and upsert opportunities into SQLite."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opportunity_engine import db
from opportunity_engine.ingest.base import IngestContext
from opportunity_engine.ingest.pipeline import ingest_source

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ingest_once")


def seed_sources_from_json(conn, path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    sources = data.get("sources") if isinstance(data, dict) else data
    count = 0
    for src in sources:
        db.upsert_source(
            conn,
            source_id=src["id"],
            name=src["name"],
            adapter=src["adapter"],
            config=src.get("config") or {},
            enabled=int(src.get("enabled", 1)),
        )
        count += 1
    conn.commit()
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest opportunities from enabled sources")
    parser.add_argument(
        "--db",
        default=str(db.DEFAULT_DB_PATH),
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--sources",
        default=str(ROOT / "data" / "sources.json"),
        help="Seed/refresh sources from this JSON before ingest",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="source_ids",
        help="Only run these source ids (repeatable)",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Do not load/refresh sources.json",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit non-zero on first source error",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    conn = db.connect(db_path)
    db.init_db(conn)

    if not args.no_seed:
        sources_path = Path(args.sources)
        if sources_path.is_file():
            n = seed_sources_from_json(conn, sources_path)
            logger.info("Seeded/updated %s sources from %s", n, sources_path)
        else:
            logger.warning("Sources file not found: %s", sources_path)

    rows = db.list_enabled_sources(conn)
    if args.source_ids:
        wanted = set(args.source_ids)
        rows = [r for r in rows if r["id"] in wanted]

    if not rows:
        logger.error("No enabled sources to ingest")
        return 1

    results = []
    with IngestContext() as ctx:
        for row in rows:
            logger.info("Ingesting %s (%s)...", row["id"], row["adapter"])
            result = ingest_source(conn, row, ctx=ctx)
            results.append(result)
            logger.info(
                "  -> status=%s seen=%s new=%s error=%s",
                result["status"],
                result["items_seen"],
                result["items_new"],
                result["error"],
            )
            if args.fail_fast and result["status"] == "error":
                break

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    total_seen = sum(r["items_seen"] for r in results)
    total_new = sum(r["items_new"] for r in results)
    live_count = conn.execute(
        "SELECT COUNT(*) AS c FROM opportunities WHERE is_demo = 0"
    ).fetchone()["c"]
    print(
        json.dumps(
            {
                "sources_run": len(results),
                "ok": ok,
                "error": err,
                "items_seen": total_seen,
                "items_new": total_new,
                "live_opportunities": live_count,
                "results": results,
            },
            indent=2,
        )
    )
    conn.close()

    # Success if at least one source ok and we have live rows (or all requested were ok)
    if ok == 0:
        return 2
    if args.fail_fast and err:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
