"""Persistence helpers: watchlist, dedupe provenance, notes."""

from __future__ import annotations

from opportunity_engine import db


def test_watchlist_partial_unknown_null(tmp_path):
    path = tmp_path / "t.db"
    conn = db.init_db(db_path=path)
    db.upsert_company(
        conn,
        id="halter",
        name="Halter",
        website="https://www.halter.io",
        location="New Zealand",
        data_quality="partial",
        monitoring_status="watching",
    )
    conn.commit()
    watch = db.get_watchlist(conn)
    assert len(watch) == 1
    assert watch[0]["data_quality"] == "partial"
    assert watch[0]["company_size"] is None
    conn.close()


def test_upsert_opportunity_dedupes(tmp_path):
    conn = db.init_db(db_path=tmp_path / "t.db")
    db.upsert_source(conn, source_id="a", name="A", adapter="manual", config={}, enabled=1)
    db.upsert_source(conn, source_id="b", name="B", adapter="manual", config={}, enabled=1)
    oid1, new1 = db.upsert_opportunity(
        conn,
        dedupe_key="ext:job-1",
        category="employment",
        title="Engineer",
        company_name="TestCo",
        company_id=None,
        location="Auckland",
        remote_ok=1,
        url="https://example.com/a",
        description="v1",
        source_id="a",
        source_url="https://example.com/a",
        posted_at=None,
        raw={"from": "a"},
        is_demo=0,
    )
    oid2, new2 = db.upsert_opportunity(
        conn,
        dedupe_key="ext:job-1",
        category="employment",
        title="Engineer",
        company_name="TestCo",
        company_id=None,
        location="Auckland",
        remote_ok=1,
        url="https://example.com/b",
        description="v2",
        source_id="b",
        source_url="https://example.com/b",
        posted_at=None,
        raw={"from": "b"},
        is_demo=0,
    )
    assert new1 and not new2 and oid1 == oid2
    assert conn.execute("SELECT COUNT(*) AS c FROM opportunities").fetchone()["c"] == 1
    raw = conn.execute("SELECT raw_json FROM opportunities").fetchone()["raw_json"]
    assert "_sources" in raw
    conn.close()


def test_update_company_notes(tmp_path):
    conn = db.init_db(db_path=tmp_path / "t.db")
    db.upsert_company(conn, id="serko", name="Serko", data_quality="partial")
    assert db.update_company_notes(
        conn, "serko", notes="Follow eng blog", interest_level=3, monitoring_status="watching"
    )
    row = conn.execute("SELECT * FROM companies WHERE id='serko'").fetchone()
    assert row["interest_level"] == 3
    assert row["notes"] == "Follow eng blog"
    conn.close()
