# Opportunity Engine — Handoff (verified end-state)

<<<<<<< HEAD
PRs **#1** (ingest), **#2** (ranking), **#3** (E2E handoff), **#4** (watchlist + UI) are on `main`. This branch expands live public source coverage.

## Verified commands
=======
PRs **#1** (ingest), **#2** (ranking), **#3** (E2E handoff), and **#4** (watchlist seed + full UI) are on `main`.

## Quickstart (current)
>>>>>>> 5bd1423 (fix(scripts): bootstrap sys.path in init_db and seed_demo)

```bash
pip install -e ".[dev]"   # or: pip install -r requirements.txt
python scripts/init_db.py
python scripts/seed.py                  # profile + watchlist (no demos)
# optional: python scripts/seed_demo.py / seed.py --with-demo
python scripts/ingest_once.py --rescore
pytest -q
uvicorn opportunity_engine.web.app:app --reload --port 8000
# UI: /  /opportunities  /companies  /skills  /actions  /sources  /profile
# API: GET /api/opportunities?min_score=3.0
```

<<<<<<< HEAD
**Baseline E2E (pre-expansion, ranking worker):** 7/7 sources ok · 418 live + 3 demo · 421 scored · API 200 with breakdowns.
=======
## Verified E2E on main (Pacific/Auckland)

Ranking-worker run @ `bee7740` / post-PR #3 (before UI merge):
>>>>>>> 5bd1423 (fix(scripts): bootstrap sys.path in init_db and seed_demo)

**Expansion smoke (PR #5):** 22 net-new enabled sources live-verified · `items_seen≈3238` · categories employment/community/entrepreneurial · CLI exit 0. Body cap 16 MiB for large boards.

Post-PR #4 UI smoke (all HTML routes + `/api/*` + company watch POST): **200 OK**.

One-shot: `python scripts/ingest_once.py --rescore`

---

## Agent A — Ingestion

**PR:** [#1](https://github.com/jxav22/opportunity-engine/pull/1) **merged**  
**Expansion:** [#5](https://github.com/jxav22/opportunity-engine/pull/5) (`cursor/expand-ingest-sources-ff5d`)

- SSRF-safe adapters: greenhouse, lever, ashby, rss, manual, github releases
- `scripts/ingest_once.py` (`--rescore` optional); live rows `is_demo=0`
- Fetch body cap **16 MiB** (scheme/IP guards unchanged)

### Seed coverage (live-verified)

**Employment (original):** Discord GH, GitLab GH, Spotify Lever, Tracksuit Ashby (NZ), Kernel Ashby (NZ), Remotive RSS, manual  
**Employment (net-new):** Anthropic/Cloudflare/Vercel/Figma/Wise GH; Palantir Lever; Auror+Xero Ashby (NZ); Linear/Cursor/PostHog/Supabase/Ramp/OpenAI Ashby  
**Community:** Show HN RSS, GitHub Blog RSS, Next.js GitHub releases  
**Entrepreneurial:** Antler accelerator RSS, Product Hunt, YC Blog, TechCrunch Funding, Idealog NZ  
**Disabled after failed live fetch:** RNZ Technology (dead feed), Creative HQ (403)

Keep helper signatures on `db.py`: `init_db`, `connect`, `upsert_source`, `list_enabled_sources`, `ensure_company`, `upsert_opportunity`, `start_ingest_run`, `finish_ingest_run`, `DEFAULT_DB_PATH`, `utc_now`.

---

## Agent B — Persistence (+ UI / D+E)

**PR:** [#4](https://github.com/jxav22/opportunity-engine/pull/4) **merged**

<<<<<<< HEAD
Owns `db.py`, `models.py`, `scripts/seed.py`, full `web/**`.
=======
**Landed (PR #4 merged):**
- Additive helpers: `upsert_company`, `get_watchlist`, `update_company_notes`, `mark_stale`, `list_opportunities`, provenance merge in `raw_json` (ingest signatures unchanged)
- `scripts/seed.py` — Auckland NZ profile + monitoring-only watchlist (`data_quality=partial`, unknown=NULL): Immersve, Halter, Partly, Tracksuit, Auror, Serko, Kernel, Trade Me, Immutable, Labrys + Xero, Sharesies; loads `data/sources.json`
- Full Jinja2+HTMX UI: Brief `/`, Inbox `/opportunities`, Companies, Skills, Actions, Sources (+ refresh→ingest+rescore), Profile HTML
- Preserved JSON APIs: `/api/opportunities`, `/api/profile`, `/api/rescore`, `/api/signals`, `/health`
>>>>>>> 5bd1423 (fix(scripts): bootstrap sys.path in init_db and seed_demo)

- Additive helpers: `upsert_company`, `get_watchlist`, `update_company_notes`, `mark_stale`, `list_opportunities` (ingest signatures unchanged)
- Full Jinja2+HTMX UI: Brief `/`, Inbox `/opportunities`, Companies, Skills, Actions, Sources, Profile
- JSON APIs preserved: `/api/opportunities`, `/api/profile`, `/api/rescore`, `/api/signals`, `/health`

---

## Agent C — Ranking

**PR:** [#2](https://github.com/jxav22/opportunity-engine/pull/2) **merged**

Profile, explainable scoring, skills, signals, actions, `rescore_all()`, AI off by default. `score_breakdown_json` = `{dimensions, penalties, blend, weights_used}`.

---

## Agents D / E

<<<<<<< HEAD
Covered by B (concurrency). UI is on main via PR #4.
=======
Covered by B (concurrency). Full Intelligence Brief / Inbox / Explorer / Skills / Actions / Sources UI is on `main` via PR #4.
>>>>>>> 5bd1423 (fix(scripts): bootstrap sys.path in init_db and seed_demo)
