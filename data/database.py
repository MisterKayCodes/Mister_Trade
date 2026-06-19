"""
database.py

Memory / Connection

Job:
Provide SQLite connections and initialize the schema.

Rules:
    - No query logic here
    - No business logic here
    - Connection settings (WAL mode, row_factory) live here and nowhere else
"""

import sqlite3
from config import DB_PATH
from data.models import ALL_TABLES, SEED_SETTINGS


def get_connection() -> sqlite3.Connection:
    """
    Return a new SQLite connection with:
      - Row factory so columns are accessible by name (row["pair"])
      - WAL journal mode for better concurrent read performance
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """
    Create all tables (if they don't exist) and seed the default
    settings row. Safe to call on every startup.
    """
    conn = get_connection()
    cursor = conn.cursor()

    for table_sql in ALL_TABLES:
        cursor.execute(table_sql)

    cursor.execute(SEED_SETTINGS)

    conn.commit()
    conn.close()
