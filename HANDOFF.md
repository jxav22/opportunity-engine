# Opportunity Engine — Handoff (end-state)

Shared integration notes. Pull/rebase often. Prefer landing on `main` via PR.

## Current main status (integration)

**Working vertical slice on `main` + integration PR:**

1. `python scripts/init_db.py`
2. `python scripts/seed_demo.py` (optional demo)
3. `python scripts/ingest_once.py --rescore`
4. `pytest -q` → ranking + ingest suites green
5. `uvicorn opportunity_engine.web.app:app --reload` → `GET /api/opportunities`

Verified end-to-end after cherry-picking Agent A ingest onto Agent C ranking: hundreds of live (`is_demo=0`) opportunities scored with breakdowns, skill_mentions, and signals.

**DB overlap:** `opportunity_engine/db.py` / `models.py` on main are contract-aligned and expose Agent A ingest helpers (`upsert_*`, `ensure_company`, `start/finish_ingest_run`, `init_db`, `connect`, `DEFAULT_DB_PATH`, `utc_now`). Persistence worker should own these files going forward — keep signatures/columns.

**UI:** Minimal FastAPI shell only. Persistence worker owns full UI (Jinja/HTMX). Do not break `/api/opportunities` JSON shape (`score_breakdown`, `quality_score`, `accessibility_score`, action fields).

**Agent A PR #1:** Conflicts with main after ranking merge; ingest was cherry-picked via integration branch rather than waiting on a dirty rebase.

---

## Agent A — Ingestion

**Branch / PR:** `cursor/agent-a-ingestion-ff5d` / [#1](https://github.com/jxav22/opportunity-engine/pull/1) (may close after integration cherry-pick lands)

### Delivered
- SSRF-safe adapters: greenhouse, lever, ashby, rss, manual, github releases
- `pipeline.py`, `scripts/ingest_once.py` (`--rescore` optional), `data/sources.json`
- Tests: `tests/test_ingest_*`

### Keep stable
`init_db`, `connect`, `upsert_source`, `list_enabled_sources`, `ensure_company`, `upsert_opportunity`, `start_ingest_run`, `finish_ingest_run`, `DEFAULT_DB_PATH`, `utc_now`

---

## Agent B — Persistence (+ UI ownership for this sprint)

**Owns:** `db.py`, `models.py`, seed/company CRUD, full UI templates when ready.

**Status:** Worker active; no separate persistence PR on main yet at last check. Schema bootstrap already on main — replace carefully, preserve columns + ingest helper signatures. Prefer enhancing `web/app.py` / templates over renaming API fields.

---

## Agent C — Ranking / profile / skills / signals / actions

**PR:** [#2](https://github.com/jxav22/opportunity-engine/pull/2) **merged** (`cursor/agent-c-ranking-f054`)

### Done
- Profile load/save (DB + `data/profile.json`), adjustable weights / 0.7–0.3 blend
- Explainable scoring: dimensions `{score, rationale, evidence[]}`, quality vs accessibility, penalties, one decimal, AI off
- Skills, signals, actions; `rescore_all()` / `python -m opportunity_engine.scoring`
- Tests: `tests/test_scoring*`, `tests/test_skills*`, `tests/test_actions_signals.py`
- Minimal `/api/opportunities` for vertical-slice testing

### Notes
- `score_breakdown_json` = `{dimensions, penalties, blend, weights_used}`
- Never auto-contact / auto-apply

---

## Agents D / E

Originally concurrency-capped. Integration + minimal API covered by ranking/persistence workers. Full HTMX Intelligence Brief / Inbox / Explorer still open for persistence/UI owner.
