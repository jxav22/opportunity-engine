# Opportunity Engine

Local-first opportunity ranking engine: ingest public job boards → explainable scores → skills/signals/actions → company watchlist.

**Stack:** Python 3.11+, FastAPI, SQLite, Jinja2+HTMX. No paid services required. AI optional and off by default.

## Quickstart

```bash
pip install -e ".[dev]"
# or: pip install -r requirements.txt  (scripts add repo root to sys.path)

python scripts/init_db.py
python scripts/seed.py                      # profile + company watchlist
python scripts/ingest_once.py --rescore     # live public boards + rank
pytest -q

uvicorn opportunity_engine.web.app:app --reload --port 8000
# open http://127.0.0.1:8000
```

Optional labeled demos (`is_demo=1`):

```bash
python scripts/seed.py --with-demo
# or: python scripts/seed_demo.py
```

## Routes

| Path | Purpose |
|------|---------|
| `/` | Intelligence Brief |
| `/opportunities` | Inbox (filters: category, saved, stale, demo, min_score) |
| `/companies`, `/companies/{id}` | Watchlist explorer + interest/notes |
| `/skills` | Skills radar |
| `/actions` | Action queue |
| `/sources` | Source health (+ refresh → ingest+rescore) |
| `/profile` | Editable profile (HTML) |
| `GET /api/opportunities` | Ranked JSON + `score_breakdown` |
| `GET\|POST /api/profile` | Profile JSON |
| `POST /api/rescore` | Recompute scores / skills / signals / actions |
| `GET /api/signals` | Early-warning signals |
| `/health` | Liveness |

## Rules

- Never fabricate company facts; unknown stays `NULL`
- Watchlist ≠ hiring claim
- Demo rows labeled (`is_demo=1`); live ingest sets `is_demo=0`

## Live sources (seeded)

Discord + GitLab (Greenhouse), Spotify (Lever), Tracksuit + Kernel (Ashby, NZ), Remotive (RSS), manual JSON. See `data/sources.json` and `HANDOFF.md` for the last verified counts.

## Ownership

See [`HANDOFF.md`](HANDOFF.md). Persistence/UI worker owns full UI and long-term `db.py` / `models.py`; keep API field names stable.
