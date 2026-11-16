"""Independent demo backend.

A *separate* FastAPI process from the personal app. It reuses ``create_app`` (so the
routes, the recommender and the evaluation code are exactly the production ones) but
points it at ``data/demo/runtime`` and adds three demo-only endpoints.

Run (from ``backend/``), after ``python -m brickwise.data.demo_ingest``::

    ../.venv/bin/uvicorn brickwise.api.demo:create_default_app --factory --port 8001

Never opens ``data/brickwise.db``. ``create_demo_app`` refuses the personal data dir.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException

from brickwise import paths
from brickwise.api import db
from brickwise.api.main import create_app, get_conn
from brickwise.data.demo_ingest import DEMO_RUNTIME_DIR, DEMO_SOURCE_DIR, assert_isolated

BANNER = "Independent demo catalogue · Fictional products · Synthetic data"
EXAMPLE_WARNING = (
    "Illustrative synthetic preferences only. Not collected from a real person and "
    "not evidence of recommendation quality."
)
# Seeding all 12 ratings would leave nothing to recommend (rated items are never
# recommended). One like and one pass are therefore held out of the example profile:
# 10 ratings (6 likes / 4 passes) still meet the evaluation minimums, and 2 products stay
# unrated so the recommender has candidates. No threshold is lowered.
EXAMPLE_HOLDOUT = ("BW-009", "BW-011")

_META_SCHEMA = "CREATE TABLE IF NOT EXISTS demo_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"


def _get_mode(conn) -> str:
    row = conn.execute("SELECT value FROM demo_meta WHERE key='profile_mode'").fetchone()
    return row["value"] if row else "fresh"


def _set_mode(conn, mode: str) -> None:
    conn.execute("INSERT INTO demo_meta(key, value) VALUES('profile_mode', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (mode,))


def load_example_profile(source_dir: Path = DEMO_SOURCE_DIR) -> dict:
    """The synthetic profile: ordered (product_id, rating) pairs from synthetic_preferences.csv."""
    meta = json.loads((Path(source_dir) / "demo_profile.json").read_text(encoding="utf-8"))
    with open(Path(source_dir) / "synthetic_preferences.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    bad = [r for r in rows if r["data_origin"] != "synthetic_not_user_feedback"]
    if bad:
        raise ValueError("synthetic_preferences.csv contains rows not marked synthetic")
    ratings = [(r["product_id"], int(r["rating"])) for r in rows if r["profile_id"] == meta["profile_id"]]
    return {"profile_id": meta["profile_id"], "description": meta["description"], "ratings": ratings}


def create_demo_app(data_dir: Optional[Path] = None, source_dir: Optional[Path] = None) -> FastAPI:
    data_dir = assert_isolated(Path(data_dir) if data_dir else DEMO_RUNTIME_DIR)
    source_dir = Path(source_dir) if source_dir else DEMO_SOURCE_DIR
    app = create_app(data_dir)
    app.title = "Brickwise Independent Demo API"
    app.state.demo = True
    conn = db.connect(app.state.db_path)
    try:
        conn.execute(_META_SCHEMA)
        conn.commit()
    finally:
        conn.close()

    @app.get("/api/demo/info")
    def demo_info(conn=Depends(get_conn)):
        profile = load_example_profile(source_dir)
        return {
            "demo": True,
            "banner": BANNER,
            "profile_mode": _get_mode(conn),   # "fresh" | "example"
            "example_profile": {
                "profile_id": profile["profile_id"],
                "description": profile["description"],
                "warning": EXAMPLE_WARNING,
                "n_ratings": len(profile["ratings"]) - len(EXAMPLE_HOLDOUT),
                "held_out": list(EXAMPLE_HOLDOUT),
            },
            "provenance": "Fictional products with original, programmatically generated artwork. "
                          "Not Rebrickable or LEGO data.",
        }

    @app.post("/api/demo/example-profile")
    def seed_example(conn=Depends(get_conn)):
        """Replace the demo feedback with the labelled synthetic example profile."""
        profile = load_example_profile(source_dir)
        known = {r[0] for r in conn.execute("SELECT set_num FROM products")}
        unknown = [pid for pid, _ in profile["ratings"] if pid not in known]
        if unknown:
            raise HTTPException(500, f"Example profile references unknown products: {unknown}")
        seeded = [(pid, r) for pid, r in profile["ratings"] if pid not in EXAMPLE_HOLDOUT]
        try:
            conn.execute("DELETE FROM feedback")
            conn.executemany("INSERT INTO feedback (set_num, rating) VALUES (?, ?)", seeded)
            _set_mode(conn, "example")
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        return {"profile_mode": "example", "seeded": len(seeded), "held_out": list(EXAMPLE_HOLDOUT),
                "warning": EXAMPLE_WARNING}

    @app.post("/api/demo/reset")
    def reset_demo(conn=Depends(get_conn)):
        """Clear demo feedback and return to a fresh demo. Affects only the demo database."""
        conn.execute("DELETE FROM feedback")
        _set_mode(conn, "fresh")
        conn.commit()
        return {"profile_mode": "fresh"}

    return app


def create_default_app() -> FastAPI:
    return create_demo_app()
