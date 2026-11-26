# Opportunity Engine — Handoff (verified end-state)

PRs **#2** (ranking), **#1** (ingest), and **#3** (E2E handoff) are on `main`. This branch adds company watchlist seed + full Jinja/HTMX UI.

## Verified E2E on main (Pacific/Auckland)

Run on `main` @ `bee7740` / post-PR #3:

```bash
pip install -e ".[dev]"   # or: pip install -r requirements.txt && pip install -e .
python scripts/init_db.py
python scripts/seed.py                  # profile + watchlist (no demos)
# optional: python scripts/seed_demo.py
python scripts/ingest_once.py --rescore
pytest -q
uvicorn opportunity_engine.web.app:app --reload --port 8000
# GET /  and  GET /api/opportunities?min_score=3.0
```

**Observed results (ranking worker run):**

| Check | Result |
|-------|--------|
| Sources | **7/7 ok** |
| Opportunities | **421** total (**418** live `is_demo=0`, **3** demo) |
| Scored | **421** with breakdowns |
| Signals | 27 |
| Skill mentions | 1439 |
| pytest | **25** passed (ingest + scoring + skills + actions) |
| `GET /api/opportunities?min_score=3.0` | **200**, breakdowns present (**72** rows) |

One-shot: `python scripts/ingest_once.py --rescore`

### Live source coverage (`data/sources.json`)

| Source id | Adapter | Board / feed | Items (this run) |
|-----------|---------|--------------|------------------|
| `gh-discord` | greenhouse | Discord public board | 30 |
| `gh-gitlab` | greenhouse | GitLab public board | 242 |
| `lever-spotify` | lever | Spotify | 97 |
| `ashby-tracksuit` | ashby | Tracksuit (NZ) | 19 |
| `ashby-kernel` | ashby | Kernel (NZ) | 12 |
| `rss-remotive` | rss | remotive.com remote jobs feed | 17 |
| `manual-seed` | manual | `data/manual_opportunities.json` | 1 |

All live rows stored with `is_demo=0`. Dead boards fail per-source without fabricating jobs.

---

## Agent A — Ingestion

**PR:** [#1](https://github.com/jxav22/opportunity-engine/pull/1) **merged**

Keep helper signatures on `db.py`: `init_db`, `connect`, `upsert_source`, `list_enabled_sources`, `ensure_company`, `upsert_opportunity`, `start_ingest_run`, `finish_ingest_run`, `DEFAULT_DB_PATH`, `utc_now`.

---

## Agent B — Persistence (+ UI / D+E)

**Owns:** `db.py`, `models.py`, `scripts/seed.py`, full `web/**`.

**Landed on this branch:**
- Additive helpers: `upsert_company`, `get_watchlist`, `update_company_notes`, `mark_stale`, `list_opportunities`, provenance merge in `raw_json` (ingest signatures unchanged)
- `scripts/seed.py` — Auckland NZ profile + monitoring-only watchlist (`data_quality=partial`, unknown=NULL): Immersve, Halter, Partly, Tracksuit, Auror, Serko, Kernel, Trade Me, Immutable, Labrys + Xero, Sharesies; loads `data/sources.json`
- Full Jinja2+HTMX UI: Brief `/`, Inbox `/opportunities`, Companies, Skills, Actions, Sources (+ refresh→ingest+rescore), Profile HTML
- Preserved JSON APIs: `/api/opportunities`, `/api/profile`, `/api/rescore`, `/api/signals`, `/health`

Do not break `/api/opportunities` field names (`score_breakdown`, `quality_score`, `accessibility_score`, action fields).

---

## Agent C — Ranking

**PR:** [#2](https://github.com/jxav22/opportunity-engine/pull/2) **merged**

Profile, explainable scoring, skills, signals, actions, `rescore_all()`, AI off by default. `score_breakdown_json` = `{dimensions, penalties, blend, weights_used}`.

---

## Agents D / E

Covered by B (concurrency). Full Intelligence Brief / Inbox / Explorer / Skills / Actions / Sources UI is in this PR.
