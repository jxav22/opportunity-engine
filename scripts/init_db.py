#!/usr/bin/env python3
"""Initialize SQLite schema (bootstrap; Agent B owns long-term)."""

from opportunity_engine.db import init_db


def main() -> None:
    conn = init_db()
    print(f"initialized: {conn.execute('PRAGMA database_list').fetchone()}")
    conn.close()


if __name__ == "__main__":
    main()
