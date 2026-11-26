#!/usr/bin/env python3
"""Initialize SQLite schema (bootstrap; Agent B owns long-term)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opportunity_engine.db import DEFAULT_DB_PATH, init_db


def main() -> None:
    conn = init_db(db_path=DEFAULT_DB_PATH)
    print(f"initialized: {DEFAULT_DB_PATH}")
    print(f"database_list: {conn.execute('PRAGMA database_list').fetchone()}")
    conn.close()


if __name__ == "__main__":
    main()
