# Opportunity Engine — Handoff (verified end-state)

PRs **#1**–**#6** (and HANDOFF cleanup **#8**) are on `main`.

## Quickstart (current)

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

## Verified E2E on main (Pacific/Auckland)

- **Baseline (pre-expansion):** 7/7 sources ok · 418 live + 3 demo · scored · API 200 with breakdowns
- **Expansion smoke (PR #5):** 29/29 enabled sources ok · `items_seen=3655` · `items_new=3238` · `live=3656` · CLI exit 0 · body cap 16 MiB
- **Post-PR #4 UI:** all HTML routes + `/api/*` + company watch POST → **200 OK**

One-shot: `python scripts/ingest_once.py --rescore`

---

## Source coverage (`data/sources.json`)

**Totals:** 31 configured · **29 enabled** · 2 disabled after failed live fetch.  
Live ingest sets `is_demo=0`. Never fabricate jobs. SSRF: http/https only; block private/link-local/metadata; body cap **16 MiB**.

### Enabled — employment

| id | adapter | board / URL key | notes |
|----|---------|-----------------|-------|
| `gh-discord` | greenhouse | `discord` | original |
| `gh-gitlab` | greenhouse | `gitlab` | original · remote-friendly |
| `gh-anthropic` | greenhouse | `anthropic` | elite eng |
| `gh-cloudflare` | greenhouse | `cloudflare` | elite / remote-friendly |
| `gh-vercel` | greenhouse | `vercel` | elite / remote-friendly |
| `gh-figma` | greenhouse | `figma` | elite product eng |
| `gh-wise` | greenhouse | `wise` | fintech |
| `lever-spotify` | lever | `spotify` | original |
| `lever-palantir` | lever | `palantir` | elite eng |
| `ashby-tracksuit` | ashby | `tracksuit` | NZ |
| `ashby-kernel` | ashby | `kernel` | NZ |
| `ashby-auror` | ashby | `auror` | NZ |
| `ashby-xero` | ashby | `xero` | NZ |
| `ashby-linear` | ashby | `linear` | elite eng |
| `ashby-cursor` | ashby | `cursor` | elite eng |
| `ashby-posthog` | ashby | `posthog` | remote-friendly |
| `ashby-supabase` | ashby | `supabase` | remote-friendly |
| `ashby-ramp` | ashby | `ramp` | high-growth eng |
| `ashby-openai` | ashby | `openai` | elite eng |
| `rss-remotive` | rss | remotive.com feed | remote jobs |
| `manual-seed` | manual | `data/manual_opportunities.json` | file registration |

### Enabled — community

| id | adapter | feed / key | notes |
|----|---------|------------|-------|
| `rss-show-hn` | rss | hnrss Show HN | launches / makers |
| `rss-github-blog` | rss | github.blog/feed | engineering community |
| `github-nextjs-releases` | github | `vercel/next.js` | OSS release atom |

### Enabled — entrepreneurial

| id | adapter | feed | notes |
|----|---------|------|-------|
| `rss-antler` | rss | antler.co blog RSS | accelerator |
| `rss-producthunt` | rss | producthunt.com/feed | launches |
| `rss-yc-blog` | rss | ycombinator.com/blog/feed | accelerator |
| `rss-tc-funding` | rss | TechCrunch funding tag | funding signals |
| `rss-idealog` | rss | idealog.co.nz/feed | NZ startup media |

### Disabled (live-fetch failed)

| id | adapter | reason |
|----|---------|--------|
| `rss-rnz-tech` | rss | dead feed (“no longer available”) |
| `rss-creative-hq` | rss | HTTP 403 via adapter |

---

## Agent A — Ingestion

**PRs:** [#1](https://github.com/jxav22/opportunity-engine/pull/1) · [#5](https://github.com/jxav22/opportunity-engine/pull/5) **merged**

- SSRF-safe adapters: greenhouse, lever, ashby, rss, manual, github releases
- `scripts/ingest_once.py` (`--rescore` optional); live rows `is_demo=0`
- Keep helper signatures on `db.py`: `init_db`, `connect`, `upsert_source`, `list_enabled_sources`, `ensure_company`, `upsert_opportunity`, `start_ingest_run`, `finish_ingest_run`, `DEFAULT_DB_PATH`, `utc_now`

---

## Agent B — Persistence (+ UI / D+E)

**PR:** [#4](https://github.com/jxav22/opportunity-engine/pull/4) **merged** · path bootstrap [#6](https://github.com/jxav22/opportunity-engine/pull/6) **merged**

- Owns `db.py`, `models.py`, `scripts/seed.py`, full `web/**`
- Additive helpers: `upsert_company`, `get_watchlist`, `update_company_notes`, `mark_stale`, `list_opportunities` (ingest signatures unchanged)
- `scripts/seed.py` — Auckland NZ profile + monitoring-only watchlist (`data_quality=partial`, unknown=NULL); loads `data/sources.json`
- Full Jinja2+HTMX UI: Brief `/`, Inbox `/opportunities`, Companies, Skills, Actions, Sources (+ refresh→ingest+rescore), Profile
- JSON APIs preserved: `/api/opportunities`, `/api/profile`, `/api/rescore`, `/api/signals`, `/health`

---

## Agent C — Ranking

**PR:** [#2](https://github.com/jxav22/opportunity-engine/pull/2) **merged**

Profile, explainable scoring, skills, signals, actions, `rescore_all()`, AI off by default. `score_breakdown_json` = `{dimensions, penalties, blend, weights_used}`.

---

## Agents D / E

Covered by B (concurrency). Full Intelligence Brief / Inbox / Explorer / Skills / Actions / Sources UI is on `main` via PR #4.
