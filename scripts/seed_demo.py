#!/usr/bin/env python3
"""Seed demo opportunities so scoring/API can be exercised offline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opportunity_engine.db import init_db
from opportunity_engine.profile import DEFAULT_PROFILE, save_profile
from opportunity_engine.scoring import rescore_all

DEMOS = [
    {
        "id": "demo-immutable-swe",
        "dedupe_key": "immutable|software engineer|remote apac",
        "category": "employment",
        "title": "Software Engineer",
        "company_id": "immutable",
        "company_name": "Immutable",
        "location": "Remote — APAC",
        "remote_ok": 1,
        "url": "https://example.com/demo/immutable",
        "description": (
            "Build player experiences with TypeScript and React on a technically "
            "demanding Web3 stack. Mentorship, ownership, exceptional engineering "
            "culture. Compensation NZD $120k–$150k + equity. NZ-friendly remote."
        ),
        "source_id": "manual",
        "discovered_at": "2026-11-10T00:00:00Z",
        "posted_at": "2026-11-08T00:00:00Z",
        "last_seen_at": "2026-11-20T00:00:00Z",
    },
    {
        "id": "demo-halter-backend",
        "dedupe_key": "halter|backend engineer|auckland",
        "category": "employment",
        "title": "Backend Engineer",
        "company_id": "halter",
        "company_name": "Halter",
        "location": "Auckland, New Zealand",
        "remote_ok": 0,
        "url": "https://example.com/demo/halter",
        "description": (
            "Distributed systems and IoT backends. Strong peers, career growth, "
            "Go and Kubernetes. On-site Auckland with flexible lifestyle."
        ),
        "source_id": "manual",
        "discovered_at": "2026-11-12T00:00:00Z",
        "posted_at": "2026-11-11T00:00:00Z",
        "last_seen_at": "2026-11-20T00:00:00Z",
    },
    {
        "id": "demo-generic-sales",
        "dedupe_key": "spam|call centre|remote",
        "category": "employment",
        "title": "Call centre representative — commission-only sales",
        "company_id": None,
        "company_name": "Generic Co",
        "location": "Remote",
        "remote_ok": 1,
        "url": "https://example.com/demo/spam",
        "description": "Get rich with guaranteed income. Pay to apply. Upfront fee required.",
        "source_id": "manual",
        "discovered_at": "2026-11-01T00:00:00Z",
        "posted_at": "2026-09-01T00:00:00Z",
        "last_seen_at": "2026-11-01T00:00:00Z",
    },
]

COMPANIES = [
    {
        "id": "immutable",
        "name": "Immutable",
        "location": "Australia / Remote",
        "industry": "Web3 gaming",
        "why_interesting": "Engineering-forward gaming/Web3 platform",
        "engineering_stack_json": '["TypeScript","React"]',
        "interest_level": 4,
        "data_quality": "demo",
        "accessibility_notes": "Remote APAC",
    },
    {
        "id": "halter",
        "name": "Halter",
        "location": "Auckland, New Zealand",
        "industry": "AgriTech",
        "why_interesting": "NZ deeptech with strong eng bar",
        "engineering_stack_json": '["Go","Kubernetes"]',
        "interest_level": 5,
        "data_quality": "demo",
        "accessibility_notes": "Auckland on-site",
    },
]


def main() -> None:
    conn = init_db()
    save_profile(DEFAULT_PROFILE, conn)
    for c in COMPANIES:
        conn.execute(
            """
            INSERT OR REPLACE INTO companies (
                id, name, location, industry, why_interesting,
                engineering_stack_json, interest_level, monitoring_status,
                data_quality, accessibility_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'watching', ?, ?, '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z')
            """,
            (
                c["id"],
                c["name"],
                c["location"],
                c["industry"],
                c["why_interesting"],
                c["engineering_stack_json"],
                c["interest_level"],
                c["data_quality"],
                c["accessibility_notes"],
            ),
        )
    for o in DEMOS:
        conn.execute(
            """
            INSERT OR REPLACE INTO opportunities (
                id, dedupe_key, category, title, company_id, company_name,
                location, remote_ok, url, description, source_id, source_url,
                discovered_at, posted_at, last_seen_at, stale, is_demo, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, 'new')
            """,
            (
                o["id"],
                o["dedupe_key"],
                o["category"],
                o["title"],
                o["company_id"],
                o["company_name"],
                o["location"],
                o["remote_ok"],
                o["url"],
                o["description"],
                o["source_id"],
                o["url"],
                o["discovered_at"],
                o["posted_at"],
                o["last_seen_at"],
            ),
        )
    conn.commit()
    summary = rescore_all(conn)
    print(summary)
    conn.close()


if __name__ == "__main__":
    main()
