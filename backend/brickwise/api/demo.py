"""Independent demo backend.

A *separate* FastAPI process from the personal app. It reuses ``create_app`` (so routes, the
recommender and the evaluation are exactly the production ones) but points it at a demo data
directory and adds demo-only endpoints. Two catalogues:

* ``fictional`` (default, public): 12 fictional products with original artwork, ``data/demo/``.
* ``real`` (local only): a frozen selection of 16 products from the user's own local catalogue,
  built by ``brickwise.data.demo_real`` into ``data/demo-real/``. Product photographs are served
  read-only straight from ``data/images/`` through an allow-listed route; nothing is copied.

Run (from ``backend/``)::

    ../.venv/bin/uvicorn brickwise.api.demo:create_default_app --factory --port 8001

``BRICKWISE_DEMO_CATALOGUE=auto|real|fictional`` (default ``auto``: real if built, else fictional).
Never opens ``data/brickwise.db`` for writing (the real builder reads it, ratings excluded).
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse

from brickwise import paths
from brickwise.api import db
from brickwise.api.main import create_app, get_conn
from brickwise.data.demo_ingest import DEMO_RUNTIME_DIR, DEMO_SOURCE_DIR, assert_isolated
from brickwise.data.demo_real import REAL_RUNTIME_DIR

BANNER = "Independent demo catalogue · Fictional products · Synthetic data"
REAL_BANNER = "Demo catalogue · Real LEGO® sets from your local Rebrickable data · Simulated example ratings"
EXAMPLE_WARNING = (
    "Illustrative synthetic preferences only. Not collected from a real person and "
    "not evidence of recommendation quality."
)
FICTIONAL_FOOTER = (
    "Brickwise independent demo: fictional products, original generated artwork and synthetic example "
    "preferences. No Rebrickable or LEGO data or images. Not affiliated with the LEGO Group or Rebrickable."
)
REAL_FOOTER = (
    "Brickwise local demo: a small selection of real LEGO® sets from your own local Rebrickable download, "
    "with photographs read from your machine. Set data and images: Rebrickable.com; "
    "images belong to their rights holders. Simulated example ratings only. Not affiliated with, or endorsed "
    "by, the LEGO Group or Rebrickable."
)
# Fictional catalogue: seeding all 12 ratings would leave nothing to recommend (rated items are never
# recommended). One like and one pass are held out: 10 ratings (6 likes / 4 passes) still meet the
# evaluation minimums and 2 products stay unrated. No threshold is lowered.
EXAMPLE_HOLDOUT = ("BW-009", "BW-011")

_META_SCHEMA = "CREATE TABLE IF NOT EXISTS demo_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"


def _get_mode(conn) -> str:
    row = conn.execute("SELECT value FROM demo_meta WHERE key='profile_mode'").fetchone()
    return row["value"] if row else "fresh"


def _set_mode(conn, mode: str) -> None:
    conn.execute("INSERT INTO demo_meta(key, value) VALUES('profile_mode', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (mode,))


def load_example_profile(source_dir: Path = DEMO_SOURCE_DIR) -> dict:
    """Fictional catalogue: ordered (product_id, rating) pairs from synthetic_preferences.csv."""
    meta = json.loads((Path(source_dir) / "demo_profile.json").read_text(encoding="utf-8"))
    with open(Path(source_dir) / "synthetic_preferences.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    bad = [r for r in rows if r["data_origin"] != "synthetic_not_user_feedback"]
    if bad:
        raise ValueError("synthetic_preferences.csv contains rows not marked synthetic")
    ratings = [(r["product_id"], int(r["rating"])) for r in rows if r["profile_id"] == meta["profile_id"]]
    return {"profile_id": meta["profile_id"], "description": meta["description"], "ratings": ratings}


def _profile(catalogue: str, source_dir: Path, data_dir: Path) -> dict:
    """Uniform {profile_id, description, warning, ratings, holdout} for either catalogue."""
    if catalogue == "real":
        p = json.loads((data_dir / "example_profile.json").read_text(encoding="utf-8"))
        return {**p, "ratings": [(s, int(r)) for s, r in p["ratings"]], "holdout": list(p["holdout"])}
    p = load_example_profile(source_dir)
    return {**p, "warning": EXAMPLE_WARNING, "holdout": list(EXAMPLE_HOLDOUT)}


def _add_read_only_image_route(app: FastAPI, images_dir: Path) -> None:
    """Replace the static /images mount with an allow-listed, GET-only route over a read-only dir."""
    app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/images"]
    root = Path(images_dir).resolve()

    @app.get("/images/{filename}")
    def real_image(filename: str, conn=Depends(get_conn)):
        row = conn.execute("SELECT image_file FROM products WHERE image_file = ?", (filename,)).fetchone()
        if row is None:
            raise HTTPException(404, "Not found")
        path = (root / row["image_file"]).resolve()
        if path.parent != root or not path.is_file():
            raise HTTPException(404, "Not found")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


def create_demo_app(data_dir: Optional[Path] = None, source_dir: Optional[Path] = None,
                    catalogue: str = "fictional", images_dir: Optional[Path] = None) -> FastAPI:
    if catalogue not in ("fictional", "real"):
        raise ValueError(f"unknown demo catalogue {catalogue!r}")
    real = catalogue == "real"
    default_dir = REAL_RUNTIME_DIR if real else DEMO_RUNTIME_DIR
    data_dir = assert_isolated(Path(data_dir) if data_dir else default_dir)
    source_dir = Path(source_dir) if source_dir else DEMO_SOURCE_DIR
    if real:
        built = (data_dir / "brickwise.db").exists() and (data_dir / "embeddings.npy").exists() \
            and (data_dir / "example_profile.json").exists()
        if not built:
            raise RuntimeError(
                f"The real demo catalogue is not built in {data_dir}. Run "
                "`python -m brickwise.data.demo_real propose`, review the contact sheet, then `freeze` and `build`; "
                "or use the fictional demo (BRICKWISE_DEMO_CATALOGUE=fictional).")
    app = create_app(data_dir)
    app.title = "Brickwise Independent Demo API"
    app.state.demo = True
    app.state.demo_catalogue = catalogue
    if real:
        _add_read_only_image_route(app, Path(images_dir) if images_dir else paths.IMAGES_DIR)
    conn = db.connect(app.state.db_path)
    try:
        conn.execute(_META_SCHEMA)
        conn.commit()
    finally:
        conn.close()

    @app.get("/api/demo/info")
    def demo_info(conn=Depends(get_conn)):
        profile = _profile(catalogue, source_dir, data_dir)
        return {
            "demo": True,
            "catalogue": catalogue,
            "banner": REAL_BANNER if real else BANNER,
            "footer": REAL_FOOTER if real else FICTIONAL_FOOTER,
            "product_count": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "profile_mode": _get_mode(conn),   # "fresh" | "example"
            "example_profile": {
                "profile_id": profile["profile_id"],
                "description": profile["description"],
                "warning": profile["warning"],
                "n_ratings": len(profile["ratings"]) - len(profile["holdout"]),
                "held_out": profile["holdout"],
            },
            "provenance": ("Real catalogue records and photographs from the local Rebrickable download, "
                           "read-only." if real else
                           "Fictional products with original, programmatically generated artwork. "
                           "Not Rebrickable or LEGO data."),
        }

    @app.post("/api/demo/example-profile")
    def seed_example(conn=Depends(get_conn)):
        """Replace the demo feedback with the labelled simulated example profile."""
        profile = _profile(catalogue, source_dir, data_dir)
        known = {r[0] for r in conn.execute("SELECT set_num FROM products")}
        unknown = [pid for pid, _ in profile["ratings"] if pid not in known]
        if unknown:
            raise HTTPException(500, f"Example profile references unknown products: {unknown}")
        seeded = [(pid, r) for pid, r in profile["ratings"] if pid not in profile["holdout"]]
        try:
            conn.execute("DELETE FROM feedback")
            conn.executemany("INSERT INTO feedback (set_num, rating) VALUES (?, ?)", seeded)
            _set_mode(conn, "example")
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        return {"profile_mode": "example", "seeded": len(seeded), "held_out": profile["holdout"],
                "warning": profile["warning"]}

    @app.post("/api/demo/reset")
    def reset_demo(conn=Depends(get_conn)):
        """Clear demo feedback and return to a fresh demo. Affects only the demo database."""
        conn.execute("DELETE FROM feedback")
        _set_mode(conn, "fresh")
        conn.commit()
        return {"profile_mode": "fresh"}

    return app


def create_default_app() -> FastAPI:
    mode = os.environ.get("BRICKWISE_DEMO_CATALOGUE", "auto").lower()
    real_dir = Path(os.environ.get("BRICKWISE_DEMO_REAL_DIR", REAL_RUNTIME_DIR))
    if mode == "auto":
        built = (real_dir / "brickwise.db").exists() and (real_dir / "embeddings.npy").exists()
        mode = "real" if built else "fictional"
    if mode == "real":
        return create_demo_app(real_dir, catalogue="real")
    if mode == "fictional":
        return create_demo_app()
    raise ValueError("BRICKWISE_DEMO_CATALOGUE must be auto, real or fictional")
