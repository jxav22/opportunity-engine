# Opportunity Engine — Handoff (verified end-state)

PRs **#2** (ranking) and **#1** (ingest) are merged to `main`. Persistence/UI worker owns full UI + long-term `db.py`/`models.py`.

## Verified E2E on main (Pacific/Auckland)

Run on `main` @ `bee7740` (after PR #1 merge):

```bash
pip install -e ".[dev]"   # or: pip install -r requirements.txt && pip install -e .
python scripts/init_db.py
python scripts/seed_demo.py
python scripts/ingest_once.py --db data/opportunity_engine.db
python -m opportunity_engine.scoring --db data/opportunity_engine.db
pytest -q
uvicorn opportunity_engine.web.app:app --reload
# GET /api/opportunities?min_score=3.0
```

**Observed results (this run):**

| Check | Result |
|-------|--------|
| Sources | **7/7 ok** |
| Opportunities | **421** total (**418** live `is_demo=0`, **3** demo) |
| Scored | **421** with breakdowns |
| Signals | 27 |
| Skill mentions | 1439 |
| pytest | **25** passed (ingest + scoring + skills + actions) |
| `GET /api/opportunities?min_score=3.0` | **200**, breakdowns present (**72** rows) |

One-shot after this PR lands: `python scripts/ingest_once.py --rescore`

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

## Agent B — Persistence (+ UI)

Owns `db.py`, `models.py`, company CRUD, full Jinja/HTMX UI. Schema bootstrap already on main — replace carefully; keep columns + ingest helpers. Do not break `/api/opportunities` field names (`score_breakdown`, `quality_score`, `accessibility_score`, action fields).

---

## Agent C — Ranking

**PR:** [#2](https://github.com/jxav22/opportunity-engine/pull/2) **merged**

Profile, explainable scoring, skills, signals, actions, `rescore_all()`, minimal API shell. AI off by default. `score_breakdown_json` = `{dimensions, penalties, blend, weights_used}`.

---

## Agents D / E

Concurrency-capped originally; vertical slice covered by ranking + ingest on main. Full Intelligence Brief / Inbox / Explorer UI still for persistence/UI owner.
