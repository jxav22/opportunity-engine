# Opportunity Engine — Handoff (verified end-state)

PRs **#1**–**#6** are on `main` (ingest, ranking, E2E handoff, watchlist+UI, expanded sources, init_db path bootstrap).

## Quickstart (current)

```bash
pip install -e ".[dev]"
# or: pip install -r requirements.txt  (scripts bootstrap repo root on sys.path)

python scripts/init_db.py
python scripts/seed.py                  # profile + watchlist (no demos)
# optional: python scripts/seed_demo.py / seed.py --with-demo
python scripts/ingest_once.py --rescore
pytest -q
uvicorn opportunity_engine.web.app:app --reload --port 8000
# UI: /  /opportunities  /companies  /skills  /actions  /sources  /profile
# API: GET /api/opportunities?min_score=3.0
```

**Baseline E2E (pre-expansion):** 7/7 sources ok · 418 live + 3 demo · 421 scored · API 200 with breakdowns.

**Expansion (PR #5):** 22 net-new enabled sources · ~29 enabled total · categories employment/community/entrepreneurial · body cap 16 MiB. Post-merge smoke: thousands of live rows ingested (CLI exit 0).

**UI smoke (PR #4):** all HTML routes + `/api/*` + company watch POST → **200 OK**.

**Scripts (PR #6):** `init_db.py` / `seed_demo.py` work with `pip install -r` (sys.path bootstrap).

One-shot: `python scripts/ingest_once.py --rescore`

---

## Agent A — Ingestion

**PR:** [#1](https://github.com/jxav22/opportunity-engine/pull/1) **merged**  
**Expansion:** [#5](https://github.com/jxav22/opportunity-engine/pull/5) **merged**

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
**Follow-up:** [#6](https://github.com/jxav22/opportunity-engine/pull/6) **merged** — `init_db.py` / `seed_demo.py` sys.path bootstrap

Owns `db.py`, `models.py`, `scripts/seed.py`, full `web/**`.

- Additive helpers: `upsert_company`, `get_watchlist`, `update_company_notes`, `mark_stale`, `list_opportunities` (ingest signatures unchanged)
- Full Jinja2+HTMX UI: Brief `/`, Inbox `/opportunities`, Companies, Skills, Actions, Sources, Profile
- JSON APIs preserved: `/api/opportunities`, `/api/profile`, `/api/rescore`, `/api/signals`, `/health`

---

## Agent C — Ranking

**PR:** [#2](https://github.com/jxav22/opportunity-engine/pull/2) **merged**

Profile, explainable scoring, skills, signals, actions, `rescore_all()`, AI off by default. `score_breakdown_json` = `{dimensions, penalties, blend, weights_used}`.

---

## Agents D / E

Covered by B (concurrency). UI is on main via PR #4.
