"""FastAPI + Jinja2 + HTMX UI, preserving Agent C JSON API contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from opportunity_engine import db as dbmod
from opportunity_engine.db import (
    get_watchlist,
    list_opportunities,
    rows_to_dicts,
    update_company_notes,
)
from opportunity_engine.profile import load_profile, profile_to_api, save_profile
from opportunity_engine.scoring import rescore_all
from opportunity_engine.signals import list_signals
from opportunity_engine.skills import skills_radar

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))

app = FastAPI(title="Opportunity Engine", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


def _db():
    return dbmod.connect(dbmod.DEFAULT_DB_PATH)


def _parse_json_field(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _banner_flags(opps: list[dict[str, Any]]) -> dict[str, bool]:
    has_demo = any(o.get("is_demo") for o in opps)
    has_live = any(not o.get("is_demo") for o in opps)
    has_stale = any(o.get("stale") for o in opps)
    return {
        "has_demo": bool(has_demo),
        "has_live": bool(has_live),
        "has_stale": bool(has_stale),
        "mixed_demo": bool(has_demo and has_live),
    }


def _ctx(**kwargs: Any) -> dict[str, Any]:
    return {"nav": kwargs.pop("nav", ""), **kwargs}


def _action_queue(conn, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM opportunities
        WHERE saved = 1 OR status = 'saved' OR next_action IS NOT NULL
        ORDER BY
            CASE WHEN saved = 1 THEN 0 ELSE 1 END,
            COALESCE(score_total, -1) DESC,
            last_seen_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return rows_to_dicts(rows)


# ---------- HTML views ----------


@app.get("/", response_class=HTMLResponse)
def brief(request: Request):
    with _db() as conn:
        profile = load_profile(conn)
        watch = rows_to_dicts(get_watchlist(conn))
        opps = rows_to_dicts(list_opportunities(conn, limit=12))
        signals = list_signals(conn, strength_threshold=0.0, include_acknowledged=True)[:8]
        actions = _action_queue(conn, limit=8)
        sources = rows_to_dicts(
            conn.execute(
                "SELECT * FROM sources ORDER BY enabled DESC, name COLLATE NOCASE"
            ).fetchall()
        )
        counts = {
            "companies": conn.execute("SELECT COUNT(*) AS n FROM companies").fetchone()["n"],
            "watching": conn.execute(
                "SELECT COUNT(*) AS n FROM companies WHERE monitoring_status='watching'"
            ).fetchone()["n"],
            "opportunities": conn.execute("SELECT COUNT(*) AS n FROM opportunities").fetchone()[
                "n"
            ],
            "demo": conn.execute(
                "SELECT COUNT(*) AS n FROM opportunities WHERE is_demo=1"
            ).fetchone()["n"],
            "live": conn.execute(
                "SELECT COUNT(*) AS n FROM opportunities WHERE is_demo=0"
            ).fetchone()["n"],
            "stale": conn.execute(
                "SELECT COUNT(*) AS n FROM opportunities WHERE stale=1"
            ).fetchone()["n"],
        }
    flags = _banner_flags(opps)
    return TEMPLATES.TemplateResponse(
        request,
        "brief.html",
        _ctx(
            nav="brief",
            profile=profile,
            watch=watch[:8],
            opportunities=opps,
            signals=signals,
            actions=actions,
            sources=sources,
            counts=counts,
            **flags,
        ),
    )


@app.get("/opportunities", response_class=HTMLResponse)
def opportunities_inbox(
    request: Request,
    category: str | None = None,
    saved: int | None = Query(None),
    stale: int | None = Query(None),
    demo: int | None = Query(None),
    min_score: float | None = Query(None),
):
    with _db() as conn:
        opps = rows_to_dicts(
            list_opportunities(
                conn,
                category=category or None,
                saved=saved,
                stale=stale,
                is_demo=demo,
                min_score=min_score,
                limit=200,
            )
        )
    flags = _banner_flags(opps)
    return TEMPLATES.TemplateResponse(
        request,
        "opportunities.html",
        _ctx(
            nav="opportunities",
            opportunities=opps,
            filters={
                "category": category or "",
                "saved": saved,
                "stale": stale,
                "demo": demo,
                "min_score": min_score if min_score is not None else "",
            },
            **flags,
        ),
    )


@app.get("/companies", response_class=HTMLResponse)
def companies_explorer(request: Request, status: str | None = Query("watching")):
    status_filter = None if status in ("", "all") else status
    with _db() as conn:
        companies = rows_to_dicts(get_watchlist(conn, status=status_filter))
    return TEMPLATES.TemplateResponse(
        request,
        "companies.html",
        _ctx(nav="companies", companies=companies, status=status or "watching"),
    )


@app.get("/companies/{company_id}", response_class=HTMLResponse)
def company_detail(request: Request, company_id: str):
    with _db() as conn:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            return HTMLResponse("Company not found", status_code=404)
        company = dict(row)
        opps = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM opportunities
                WHERE company_id = ? OR lower(company_name) = lower(?)
                ORDER BY COALESCE(score_total, -1) DESC, last_seen_at DESC
                """,
                (company_id, company["name"]),
            ).fetchall()
        )
        developments = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM company_developments
                WHERE company_id = ?
                ORDER BY observed_at DESC
                """,
                (company_id,),
            ).fetchall()
        )
    flags = _banner_flags(opps)
    return TEMPLATES.TemplateResponse(
        request,
        "company_detail.html",
        _ctx(
            nav="companies",
            company=company,
            opportunities=opps,
            developments=developments,
            **flags,
        ),
    )


@app.post("/companies/{company_id}/watch")
def company_watch(
    company_id: str,
    interest_level: int = Form(0),
    monitoring_status: str = Form("watching"),
    notes: str = Form(""),
):
    with _db() as conn:
        ok = update_company_notes(
            conn,
            company_id,
            notes=notes or None,
            interest_level=max(0, min(5, interest_level)),
            monitoring_status=monitoring_status,
        )
        conn.commit()
    if not ok:
        return HTMLResponse("Company not found", status_code=404)
    return RedirectResponse(url=f"/companies/{company_id}", status_code=303)


@app.get("/skills", response_class=HTMLResponse)
def skills_page(request: Request):
    with _db() as conn:
        profile = load_profile(conn)
        radar = skills_radar(conn, profile)
    # Adapt to template expecting demand list
    demand = [
        {"skill": f["skill"], "mentions": f["count"]}
        for f in radar.get("frequency", [])
    ]
    return TEMPLATES.TemplateResponse(
        request,
        "skills.html",
        _ctx(nav="skills", demand=demand, radar=radar),
    )


@app.get("/actions", response_class=HTMLResponse)
def actions_page(request: Request):
    with _db() as conn:
        items = _action_queue(conn)
    return TEMPLATES.TemplateResponse(
        request,
        "actions.html",
        _ctx(nav="actions", actions=items),
    )


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request):
    with _db() as conn:
        sources = rows_to_dicts(
            conn.execute(
                "SELECT * FROM sources ORDER BY enabled DESC, name COLLATE NOCASE"
            ).fetchall()
        )
        runs = rows_to_dicts(
            conn.execute(
                "SELECT * FROM ingest_runs ORDER BY started_at DESC LIMIT 20"
            ).fetchall()
        )
    return TEMPLATES.TemplateResponse(
        request,
        "sources.html",
        _ctx(nav="sources", sources=sources, runs=runs),
    )


@app.post("/sources/refresh")
def sources_refresh():
    ingest_script = Path(__file__).resolve().parents[2] / "scripts" / "ingest_once.py"
    message = "ingest_once.py missing"
    status = "pending"
    if ingest_script.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(ingest_script)],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(ingest_script.parent.parent),
            )
            status = "ok" if result.returncode == 0 else "error"
            message = (result.stdout or result.stderr or status)[-500:]
            if result.returncode == 0:
                try:
                    rescore_all()
                    message = "ingest+rescore ok"
                except Exception as exc:  # noqa: BLE001
                    message = f"ingest ok; rescore failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            status = "error"
            message = str(exc)
    return RedirectResponse(
        url=f"/sources?refresh={status}&msg={quote(message[:200])}",
        status_code=303,
    )


@app.get("/profile", response_class=HTMLResponse)
def profile_get(request: Request):
    with _db() as conn:
        profile = load_profile(conn)
    return TEMPLATES.TemplateResponse(
        request,
        "profile.html",
        _ctx(
            nav="profile",
            profile_json=json.dumps(profile, indent=2, ensure_ascii=False),
            error=None,
            saved=False,
        ),
    )


@app.post("/profile", response_class=HTMLResponse)
async def profile_post(request: Request, profile_json: str = Form(...)):
    error = None
    saved = False
    try:
        body = json.loads(profile_json)
        if not isinstance(body, dict):
            raise ValueError("Profile must be a JSON object")
        with _db() as conn:
            profile = save_profile(body, conn)
        saved = True
        rendered = json.dumps(profile, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError) as exc:
        rendered = profile_json
        error = str(exc)
    return TEMPLATES.TemplateResponse(
        request,
        "profile.html",
        _ctx(nav="profile", profile_json=rendered, error=error, saved=saved),
    )


# ---------- JSON APIs (Agent C contracts) ----------


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
        return JSONResponse(
            {"signals": list_signals(conn, strength_threshold=min_strength)}
        )
    finally:
        conn.close()


@app.get("/api/profile")
def api_get_profile() -> JSONResponse:
    conn = dbmod.connect()
    try:
        return JSONResponse(profile_to_api(load_profile(conn)))
    finally:
        conn.close()


@app.post("/api/profile")
async def api_post_profile(body: dict[str, Any]) -> JSONResponse:
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
    db_path = Path(dbmod.DEFAULT_DB_PATH)
    dbmod.init_db(db_path=db_path)
    return app
