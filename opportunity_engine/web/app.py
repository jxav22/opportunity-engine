"""Minimal API/UI routes — Agent D owns full UI; this enables vertical-slice tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from opportunity_engine import db as dbmod
from opportunity_engine.profile import load_profile, profile_to_api, save_profile
from opportunity_engine.scoring import rescore_all
from opportunity_engine.signals import list_signals

app = FastAPI(title="Opportunity Engine", version="0.1.0")


def _parse_json_field(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


@app.get("/", response_class=HTMLResponse)
def intelligence_brief() -> str:
    return """<!doctype html>
<html><head><title>Opportunity Engine</title></head>
<body>
  <h1>Opportunity Engine</h1>
  <p>Minimal shell — full UI owned by Agent D.</p>
  <ul>
    <li><a href="/api/opportunities">/api/opportunities</a></li>
    <li><a href="/profile">/profile</a></li>
    <li><a href="/api/signals">/api/signals</a></li>
  </ul>
</body></html>"""


@app.get("/api/opportunities")
def api_opportunities(
    category: str | None = None,
    saved: int | None = None,
    stale: int | None = None,
    demo: int | None = None,
    min_score: float | None = Query(default=None),
) -> JSONResponse:
    conn = dbmod.connect()
    try:
        sql = "SELECT * FROM opportunities WHERE 1=1"
        params: list[Any] = []
        if category:
            sql += " AND category = ?"
            params.append(category)
        if saved is not None:
            sql += " AND saved = ?"
            params.append(saved)
        if stale is not None:
            sql += " AND stale = ?"
            params.append(stale)
        if demo is not None:
            sql += " AND is_demo = ?"
            params.append(demo)
        if min_score is not None:
            sql += " AND score_total >= ?"
            params.append(min_score)
        sql += " ORDER BY score_total IS NULL, score_total DESC, discovered_at DESC"
        rows = conn.execute(sql, params).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["score_breakdown"] = _parse_json_field(
                item.pop("score_breakdown_json", None), {}
            )
            item["skills"] = _parse_json_field(item.pop("skills_json", None), [])
            item["uncertainties"] = _parse_json_field(
                item.pop("uncertainties_json", None), []
            )
            item["raw"] = _parse_json_field(item.pop("raw_json", None), None)
            items.append(item)
        return JSONResponse({"opportunities": items, "count": len(items)})
    finally:
        conn.close()


@app.get("/api/signals")
def api_signals(min_strength: float = 0.55) -> JSONResponse:
    conn = dbmod.connect()
    try:
        return JSONResponse({"signals": list_signals(conn, strength_threshold=min_strength)})
    finally:
        conn.close()


@app.get("/profile")
@app.get("/api/profile")
def get_profile() -> JSONResponse:
    conn = dbmod.connect()
    try:
        return JSONResponse(profile_to_api(load_profile(conn)))
    finally:
        conn.close()


@app.post("/profile")
@app.post("/api/profile")
async def post_profile(body: dict[str, Any]) -> JSONResponse:
    conn = dbmod.connect()
    try:
        saved = save_profile(body, conn)
        return JSONResponse(profile_to_api(saved))
    finally:
        conn.close()


@app.post("/api/rescore")
def api_rescore() -> JSONResponse:
    summary = rescore_all()
    return JSONResponse(summary)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> FastAPI:
    # Ensure schema exists for local runs.
    db_path = Path(dbmod.DEFAULT_DB_PATH)
    dbmod.init_db(db_path=db_path)
    return app
