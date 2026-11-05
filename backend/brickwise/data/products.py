"""Products table access (written only by ingestion; read-only for everyone else)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .. import paths

COLUMNS = ["set_num", "name", "year", "theme_id", "theme", "root_theme",
           "num_parts", "img_url", "image_file"]


def _db_path(db_path=None) -> Path:
    # Resolve DATA_DIR lazily so BRICKWISE_DATA_DIR set after import is honoured.
    if db_path is not None:
        return Path(db_path)
    import os
    env = os.environ.get("BRICKWISE_DATA_DIR")
    return (Path(env) / "brickwise.db") if env else paths.DB_PATH


def connect(db_path=None) -> sqlite3.Connection:
    p = _db_path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(paths.SCHEMA_PATH.read_text())


def write_products(con: sqlite3.Connection, rows: Iterable[dict]) -> int:
    """Upsert rows; remove stale products not referenced by feedback. Returns count."""
    rows = list(rows)
    init_db(con)
    con.executemany(
        f"INSERT INTO products ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))}) "
        "ON CONFLICT(set_num) DO UPDATE SET "
        + ",".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "set_num"),
        [tuple(r[c] for c in COLUMNS) for r in rows],
    )
    keep = [r["set_num"] for r in rows]
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _keep(set_num TEXT PRIMARY KEY)")
    con.execute("DELETE FROM _keep")
    con.executemany("INSERT OR IGNORE INTO _keep VALUES (?)", [(k,) for k in keep])
    con.execute("DELETE FROM products WHERE set_num NOT IN (SELECT set_num FROM _keep) "
                "AND set_num NOT IN (SELECT set_num FROM feedback)")
    con.commit()
    return len(rows)


def load_products(db_path=None) -> list[dict]:
    """Return all products as dicts (keys per schema), ordered by set_num."""
    p = _db_path(db_path)
    if not p.exists():
        return []
    con = connect(p)
    try:
        cur = con.execute(f"SELECT {','.join(COLUMNS)} FROM products ORDER BY set_num")
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()
