"""SQLite helpers: per-request connections, schema bootstrap, row mappers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from brickwise.paths import SCHEMA_PATH


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    """Apply schema.sql (all statements are CREATE IF NOT EXISTS)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(Path(SCHEMA_PATH).read_text())
        conn.commit()
    finally:
        conn.close()


def product_from_row(row: sqlite3.Row) -> dict:
    return {
        "set_num": row["set_num"],
        "name": row["name"],
        "year": row["year"],
        "theme": row["theme"],
        "root_theme": row["root_theme"],
        "num_parts": row["num_parts"],
        "image_url": f"/images/{row['image_file']}",
    }


def feedback_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "set_num": row["set_num"],
        "rating": row["rating"],
        "created_at": row["created_at"],
    }
