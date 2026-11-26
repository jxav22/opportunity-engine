# opportunity-engine

Local-first opportunity ranking engine (FastAPI + SQLite).

## Quick start

```bash
pip install -e ".[dev]"
python scripts/init_db.py
python scripts/seed_demo.py
pytest -q
uvicorn opportunity_engine.web.app:app --reload
```

- Profile: `GET|POST /profile`
- Ranked JSON: `GET /api/opportunities`
- Rescore: `POST /api/rescore` or `python -m opportunity_engine.scoring`

See `HANDOFF.md` for agent ownership.
