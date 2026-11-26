# opportunity-engine

Local-first opportunity ranking engine: ingest public job boards → explainable scores → skills/signals/actions.

**Stack:** Python 3.11+, FastAPI, SQLite, Jinja2/HTMX-ready API. No paid services required. AI optional and off by default.

## Quick start (vertical slice)

```bash
pip install -e ".[dev]"
# or: pip install -r requirements.txt && pip install -e .

python scripts/init_db.py
python scripts/seed_demo.py          # optional demo rows (is_demo=1)
python scripts/ingest_once.py --rescore
pytest -q

uvicorn opportunity_engine.web.app:app --reload
```

Then open:

| Route | Purpose |
|-------|---------|
| `GET /` | Minimal brief shell |
| `GET /api/opportunities` | Ranked JSON + `score_breakdown` |
| `GET\|POST /profile` | Editable profile / ranking weights |
| `POST /api/rescore` | Recompute scores/skills/signals/actions |
| `GET /api/signals` | Early-warning signals |

## What works today

- **Ingest:** Greenhouse, Lever, Ashby, RSS, manual JSON (SSRF-safe fetch)
- **Ranking:** Deterministic dimensions with rationales + evidence; separate quality vs accessibility; penalties
- **Skills / signals / actions:** Extracted on rescore; never auto-apply or auto-contact
- **Persistence:** SQLite schema matching shared contracts (`opportunity_engine/db.py`)

## Verify live data

```bash
python scripts/ingest_once.py --db data/opportunity_engine.db --rescore
python -c "import sqlite3; c=sqlite3.connect('data/opportunity_engine.db'); print(c.execute('select count(*), sum(is_demo=0), sum(score_total is not null) from opportunities').fetchone())"
```

## Agent ownership

See [`HANDOFF.md`](HANDOFF.md). Persistence/UI worker owns full Jinja+HTMX UI and long-term `db.py`/`models.py`; keep `/api/opportunities` field names stable.
