#!/usr/bin/env python3
"""Seed profile, company watchlist, optional demo opportunities, and placeholder sources."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opportunity_engine.db import (
    DEFAULT_DB_PATH,
    connect,
    init_db,
    upsert_company,
    upsert_opportunity,
    upsert_source,
)
from opportunity_engine.profile import DEFAULT_PROFILE, save_profile


# Monitoring targets ONLY — never claim hiring. Unknown fields stay NULL.
# website left only when publicly well-known; all other facts omitted.
WATCHLIST = [
    {
        "id": "immersve",
        "name": "Immersve",
        "website": "https://www.immersve.com",
        "location": "New Zealand",
        "industry": None,
        "why_interesting": "NZ Web3 / payments-adjacent; on watchlist for engineering culture signals.",
    },
    {
        "id": "halter",
        "name": "Halter",
        "website": "https://www.halter.io",
        "location": "New Zealand",
        "industry": None,
        "why_interesting": "Hardware+software NZ scale-up; monitoring for engineering roles and product signals.",
    },
    {
        "id": "partly",
        "name": "Partly",
        "website": "https://www.partly.com",
        "location": "New Zealand",
        "industry": None,
        "why_interesting": "NZ marketplace/infra company; watch for stack and hiring signals.",
    },
    {
        "id": "tracksuit",
        "name": "Tracksuit",
        "website": "https://www.tracksuit.com",
        "location": "New Zealand",
        "industry": None,
        "why_interesting": "NZ brand-tracking SaaS; monitoring target only.",
    },
    {
        "id": "auror",
        "name": "Auror",
        "website": "https://www.auror.co",
        "location": "New Zealand",
        "industry": None,
        "why_interesting": "NZ SaaS; on watchlist — no hiring claim.",
    },
    {
        "id": "serko",
        "name": "Serko",
        "website": "https://www.serko.com",
        "location": "New Zealand",
        "industry": None,
        "why_interesting": "NZ travel-tech listed company; monitoring target.",
    },
    {
        "id": "kernel",
        "name": "Kernel",
        "website": "https://www.kernelwealth.co.nz",
        "location": "New Zealand",
        "industry": None,
        "why_interesting": "NZ fintech / wealth; monitoring for engineering signals.",
    },
    {
        "id": "trade-me",
        "name": "Trade Me",
        "website": "https://www.trademe.co.nz",
        "location": "New Zealand",
        "industry": None,
        "why_interesting": "Large NZ consumer marketplace; monitoring target.",
    },
    {
        "id": "immutable",
        "name": "Immutable",
        "website": "https://www.immutable.com",
        "location": "Australia",
        "industry": None,
        "why_interesting": "AU Web3 / gaming infra; relevant to Web3 interests — monitoring only.",
    },
    {
        "id": "labrys",
        "name": "Labrys",
        "website": "https://labrys.io",
        "location": "Australia",
        "industry": None,
        "why_interesting": "AU Web3 studio; monitoring target for DeFi/Web3 craft.",
    },
    # Sensible peers (still monitoring only; unknown facts NULL)
    {
        "id": "xero",
        "name": "Xero",
        "website": "https://www.xero.com",
        "location": "New Zealand",
        "industry": None,
        "why_interesting": "NZ SaaS peer; monitoring for engineering culture benchmarks.",
    },
    {
        "id": "sharesies",
        "name": "Sharesies",
        "website": "https://www.sharesies.nz",
        "location": "New Zealand",
        "industry": None,
        "why_interesting": "NZ fintech peer; monitoring target.",
    },
]


def seed_profile(conn, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    profile_path = data_dir / "profile.json"
    if profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    else:
        profile = DEFAULT_PROFILE
    save_profile(profile, conn, path=profile_path, also_file=True)
    print(f"Seeded profile → DB + {profile_path}")


def seed_watchlist(conn) -> int:
    count = 0
    for c in WATCHLIST:
        upsert_company(
            conn,
            id=c["id"],
            name=c["name"],
            website=c.get("website"),
            location=c.get("location"),
            industry=c.get("industry"),
            product_description=None,
            engineering_stack_json=None,
            company_size=None,
            funding_stage=None,
            remote_policy=None,
            accessibility_notes=None,
            why_interesting=c.get("why_interesting"),
            source_links_json=None,
            last_verified_at=None,
            interest_level=0,
            monitoring_status="watching",
            notes=None,
            data_quality="partial",
        )
        count += 1
    print(f"Seeded {count} watchlist companies (monitoring only, data_quality=partial)")
    return count


def seed_sources(conn) -> None:
    """Load Agent A sources.json when present; ensure demo-seed exists for demos."""
    sources_path = ROOT / "data" / "sources.json"
    if sources_path.is_file():
        data = json.loads(sources_path.read_text(encoding="utf-8"))
        sources = data.get("sources") if isinstance(data, dict) else data
        for src in sources:
            upsert_source(
                conn,
                source_id=src["id"],
                name=src["name"],
                adapter=src["adapter"],
                config=src.get("config") or {},
                enabled=int(src.get("enabled", 1)),
            )
        print(f"Seeded/updated {len(sources)} sources from {sources_path}")
    else:
        print(f"No {sources_path}; skipping live source seed")

    # Demo source for optional is_demo rows (disabled so ingest_once won't fetch it)
    upsert_source(
        conn,
        source_id="demo-seed",
        name="Demo seed source",
        adapter="manual",
        config={"demo": True},
        enabled=0,
    )


def seed_demo_opportunities(conn, *, include_demo: bool) -> int:
    if not include_demo:
        print("Skipping demo opportunities (--no-demo)")
        return 0

    demos = [
        {
            "title": "[DEMO] Software Engineer",
            "company_id": "immutable",
            "company_name": "Immutable",
            "location": "Remote (AU/NZ)",
            "url": "https://example.com/demo/immutable-swe",
            "description": (
                "DEMO ONLY — illustrative listing. Not a real open role. "
                "Used to exercise ranking/UI until live ingest is configured."
            ),
            "category": "employment",
            "skills": ["TypeScript", "Web3", "full-stack"],
        },
        {
            "title": "[DEMO] Backend Engineer (.NET)",
            "company_id": "serko",
            "company_name": "Serko",
            "location": "Auckland, New Zealand",
            "url": "https://example.com/demo/serko-dotnet",
            "description": (
                "DEMO ONLY — illustrative listing. Not a real open role."
            ),
            "category": "employment",
            "skills": ["C#", ".NET", "full-stack"],
        },
        {
            "title": "[DEMO] Emerging company watch — Halter",
            "company_id": "halter",
            "company_name": "Halter",
            "location": "New Zealand",
            "url": "https://www.halter.io",
            "description": (
                "DEMO ONLY — emerging-company card for UI/scoring rehearsal. "
                "Does not claim Halter is hiring."
            ),
            "category": "emerging_company",
            "skills": [],
        },
    ]
    n = 0
    for d in demos:
        ext = f"demo:{d['company_id']}:{d['title']}"
        upsert_opportunity(
            conn,
            dedupe_key=f"ext:{ext.lower()}",
            category=d["category"],
            title=d["title"],
            company_name=d["company_name"],
            company_id=d["company_id"],
            location=d["location"],
            remote_ok=None,
            url=d["url"],
            description=d["description"],
            source_id="demo-seed",
            source_url=d["url"],
            posted_at=None,
            raw={"demo": True, "label": "DEMO — not live data", "skills": d["skills"]},
            is_demo=1,
        )
        n += 1
    print(f"Seeded {n} clearly labeled demo opportunities (is_demo=1)")
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Opportunity Engine data")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--no-demo",
        action="store_true",
        help="Do not insert demo opportunities (live table stays empty of demos)",
    )
    parser.add_argument(
        "--with-demo",
        action="store_true",
        help="Insert a few labeled demo opportunities (opt-in labeled demos)",
    )
    args = parser.parse_args()

    # Live-first: demos only with --with-demo
    include_demo = bool(args.with_demo) and not args.no_demo

    conn = init_db(db_path=args.db)
    conn.close()
    data_dir = ROOT / "data"
    with connect(args.db) as conn:
        seed_profile(conn, data_dir)
        seed_watchlist(conn)
        seed_sources(conn)
        seed_demo_opportunities(conn, include_demo=include_demo)
        conn.commit()

        watch = conn.execute(
            "SELECT COUNT(*) AS n FROM companies WHERE monitoring_status='watching'"
        ).fetchone()["n"]
        opps = conn.execute("SELECT COUNT(*) AS n FROM opportunities").fetchone()["n"]
        print(f"Done. watchlist={watch} opportunities={opps} db={args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
