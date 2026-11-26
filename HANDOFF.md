# Opportunity Engine — Handoff

Shared integration notes across agents. Pull/rebase often.

## Agent A — Source adapters / ingestion

**Branch:** `cursor/agent-a-ingestion-ff5d`  
**PR:** https://github.com/jxav22/opportunity-engine/pull/1  
**Status:** Rebased onto main after Agent C merge. Live verified ≥3 sources (Discord GH, Spotify Lever, Tracksuit/Kernel Ashby, Remotive RSS, manual). Prefers main’s `db.py`/`models.py`.

### Delivered
- `opportunity_engine/ingest/base.py` — `SourceAdapter` protocol, `RawItem`, `IngestContext`, SSRF-safe `safe_get` (http/https only; block private/link-local/metadata; timeouts; politeness delay)
- Adapters: `greenhouse`, `lever`, `ashby`, `rss` (feedparser), `manual` (JSON/file), `github` (releases atom via RSS)
- `pipeline.py` — normalize → dedupe_key → company linkage → opportunity upsert; `ingest_runs` + source health
- `scripts/ingest_once.py` — CLI seeds `data/sources.json`, runs enabled sources, prints JSON summary, exit 0 if ≥1 source ok
- Seeds (verified live): Discord Greenhouse, GitLab Greenhouse, Spotify Lever, Tracksuit Ashby (NZ), Kernel Ashby (NZ), Remotive RSS, manual file
- Live rows always `is_demo=0`; no fabricated jobs
- Tests: `tests/test_ingest_*`

### Notes for others
- Keep helper signatures: `init_db`, `connect`, `upsert_source`, `list_enabled_sources`, `ensure_company`, `upsert_opportunity`, `start_ingest_run`, `finish_ingest_run`, `DEFAULT_DB_PATH`, `utc_now`
- Dead boards fail per-source gracefully; CLI still exits 0 if other sources succeed
- Rate limit: default 0.4s between fetches in `IngestContext`
- Depends on `feedparser` (in `requirements.txt` / should be in `pyproject.toml` deps)

### Verify
```bash
pip install -r requirements.txt
# or: pip install -e ".[dev]" && pip install feedparser
python scripts/ingest_once.py --db data/opportunity_engine.db
pytest tests/test_ingest* -q
```

## Agent B — Persistence
_Status: coordinate on main._ Schema bootstrap in `opportunity_engine/db.py` (contract-aligned, includes Agent A ingest helpers) so ranking/API/ingest can run. **Agent B should take ownership** of `db.py` / `models.py` / seed scripts; Agent C will rebase onto B’s schema without changing column names.

## Agent C — Ranking / profile / skills / signals / actions

**Branch:** `cursor/agent-c-ranking-f054` (ranking workstream; was `agent-c-ranking`)  
**Owns:** `opportunity_engine/{scoring,profile,skills,signals,actions}.py`, `tests/test_scoring*`, `tests/test_skills*`

### Done
- **Profile:** load/save editable JSON via SQLite `profile` table + `data/profile.json`; `normalize_profile`, `profile_to_api`, adjustable `ranking_weights` + `score_blend` (default 0.7/0.3).
- **Scoring:** deterministic explainable ranking. Each dimension → `{score, rationale, evidence[]}`. Separate `quality_score` vs `accessibility_score`. `score_total` blend. Penalties: geo, unrealistic seniority, stale, weak evidence, dubious, generic low-value, misleading comp, high upfront cost. One-decimal scores. Credential-free (AI off).
- **Skills:** curated taxonomy + light heuristics; `skill_mentions` writes; frequency analysis; profile compare; upskilling priorities that prefer high-leverage / high-score-role skills over mere frequency. No historical trend claims.
- **Signals:** first eng vacancy, funding, NZ hiring, accelerator open, relevant event; dedupe vs prior; strength threshold (default 0.55).
- **Actions:** Apply/Investigate/Monitor/Attend/Learn/Build/Introduce/OSS for high-priority ops; fills next_action, rationales, evidence_summary, uncertainties. Never auto-contact/auto-apply.
- **`rescore_all()`** (+ `python -m opportunity_engine.scoring` / `oe-rescore`) after ingest.
- **Tests:** determinism + skills + actions/signals.
- **Vertical slice:** minimal FastAPI `/api/opportunities` (includes score breakdowns), `/api/rescore`, `/profile` because Agents D/E were concurrency-capped.

### How to verify
```bash
pip install -e ".[dev]"
pytest -q
python scripts/seed_demo.py
uvicorn opportunity_engine.web.app:app --reload
# GET /api/opportunities
```

### Notes for integrators
- `score_breakdown_json` stores `{dimensions, penalties, blend, weights_used}`.
- AI optional and **OFF** by default — not used in scoring path.
- If Agent B replaces `db.py`, keep column names from contracts; ranking modules only assume those columns.

## Agent D — UI
_Not started (concurrency). Minimal API shell in `opportunity_engine/web/app.py` for testing; D should replace with full Jinja/HTMX UI without breaking `/api/opportunities` field names._

## Agent E — Integration
_Not started (concurrency)._
