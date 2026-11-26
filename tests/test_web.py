"""UI + API smoke tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opportunity_engine import db
from opportunity_engine.profile import save_profile
from opportunity_engine.web import app as webapp


@pytest.fixture()
def client(tmp_path, monkeypatch):
    path = tmp_path / "web.db"
    conn = db.init_db(db_path=path)
    save_profile({"name": "Test", "location": "Auckland"}, conn)
    db.upsert_company(
        conn, id="tracksuit", name="Tracksuit", data_quality="partial", location="New Zealand"
    )
    db.upsert_source(
        conn, source_id="demo-seed", name="Demo", adapter="manual", config={}, enabled=0
    )
    db.upsert_opportunity(
        conn,
        dedupe_key="ext:demo-1",
        category="employment",
        title="[DEMO] Engineer",
        company_name="Tracksuit",
        company_id="tracksuit",
        location="Auckland",
        remote_ok=None,
        url="https://example.com/demo",
        description="demo",
        source_id="demo-seed",
        source_url="https://example.com/demo",
        posted_at=None,
        raw={"demo": True},
        is_demo=1,
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", path)
    return TestClient(webapp.app)


def test_brief_inbox_api(client):
    assert client.get("/").status_code == 200
    r = client.get("/opportunities")
    assert r.status_code == 200
    assert b"[DEMO] Engineer" in r.content
    data = client.get("/api/opportunities").json()
    assert "opportunities" in data and data["count"] >= 1


def test_companies_profile_health(client):
    assert client.get("/companies").status_code == 200
    assert client.get("/companies/tracksuit").status_code == 200
    assert client.get("/profile").status_code == 200
    assert client.get("/api/profile").json()["name"]
    assert client.get("/health").json()["status"] == "ok"
