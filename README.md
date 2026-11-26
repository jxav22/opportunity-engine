# opportunity-engine

Local-first opportunity ranking engine: ingest public job boards → explainable scores → skills/signals/actions.

**Stack:** Python 3.11+, FastAPI, SQLite. No paid services required. AI optional and off by default.

## Quick start

```bash
pip install -e ".[dev]"

python scripts/init_db.py
python scripts/seed_demo.py                 # optional demo rows (is_demo=1)
python scripts/ingest_once.py --rescore     # live public boards + rank
pytest -q

uvicorn opportunity_engine.web.app:app --reload
```

| Route | Purpose |
|-------|---------|
| `GET /api/opportunities` | Ranked JSON + `score_breakdown` |
| `GET\|POST /profile` | Editable profile / ranking weights |
| `POST /api/rescore` | Recompute scores / skills / signals / actions |
| `GET /api/signals` | Early-warning signals |

## Live sources (seeded)

Discord + GitLab (Greenhouse), Spotify (Lever), Tracksuit + Kernel (Ashby, NZ), Remotive (RSS), manual JSON. See `data/sources.json` and `HANDOFF.md` for the last verified counts.

## Ownership

See [`HANDOFF.md`](HANDOFF.md). Persistence/UI worker owns full UI and long-term `db.py` / `models.py`; keep API field names stable.
