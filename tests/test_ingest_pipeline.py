"""Pipeline upsert + ingest_run integration tests."""

from __future__ import annotations

import json
import sqlite3

from opportunity_engine import db
from opportunity_engine.ingest.base import IngestContext, RawItem
from opportunity_engine.ingest.pipeline import ingest_source


class _FakeAdapter:
    name = "manual"

    def fetch(self, config: dict, ctx: IngestContext) -> list[RawItem]:
        return [
            RawItem(
                external_id="t1",
                title="Software Engineer",
                url="https://example.com/jobs/1",
                company_name="TestCo",
                location="Auckland, New Zealand",
                description="Build things",
                posted_at="2026-01-01T00:00:00Z",
                category="employment",
                raw={"id": "t1"},
            ),
            RawItem(
                external_id="t1",
                title="Software Engineer",
                url="https://example.com/jobs/1",
                company_name="TestCo",
                location="Auckland, New Zealand",
                description="Build things",
                posted_at="2026-01-01T00:00:00Z",
                category="employment",
                raw={"id": "t1"},
            ),
        ]


def test_ingest_source_dedupes(monkeypatch, tmp_path):
    from opportunity_engine.ingest import registry

    monkeypatch.setitem(registry.ADAPTERS, "manual", _FakeAdapter())

    db_path = tmp_path / "t.db"
    conn = db.connect(db_path)
    db.init_db(conn)
    db.upsert_source(
        conn,
        source_id="manual-test",
        name="Manual Test",
        adapter="manual",
        config={"items": []},
        enabled=1,
    )
    conn.commit()

    row = conn.execute("SELECT * FROM sources WHERE id = ?", ("manual-test",)).fetchone()
    result = ingest_source(conn, row, ctx=IngestContext())
    assert result["status"] == "ok"
    assert result["items_seen"] == 2
    assert result["items_new"] == 1

    count = conn.execute("SELECT COUNT(*) AS c FROM opportunities").fetchone()["c"]
    assert count == 1
    demo = conn.execute("SELECT is_demo FROM opportunities").fetchone()["is_demo"]
    assert demo == 0
    run = conn.execute("SELECT * FROM ingest_runs").fetchone()
    assert run["status"] == "ok"
    assert run["items_new"] == 1
    src = conn.execute("SELECT last_success_at, last_error FROM sources").fetchone()
    assert src["last_success_at"]
    assert src["last_error"] is None
