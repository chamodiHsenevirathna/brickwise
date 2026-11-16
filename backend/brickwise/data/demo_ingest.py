"""Isolated ingestion of the independent, fictional demo catalogue.

Reads ``data/demo/products.csv`` + ``data/demo/images/`` (original artwork, see
``demo_artwork.py``) and builds a *separate* runtime directory::

    data/demo/runtime/{brickwise.db, images/, embeddings.npy, embedding_ids.json}

Nothing here reads or writes the personal catalogue (``data/brickwise.db``,
``data/images/``, ``data/embeddings.npy``). ``ingest_demo`` refuses to run if the
target directory is, or contains, the personal data directory.

Run (from ``backend/``)::

    ../.venv/bin/python -m brickwise.data.demo_ingest
"""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

from .. import paths
from . import products as products_db
from ..ml import embeddings as emb

DEMO_SOURCE_DIR = paths.ROOT / "data" / "demo"
DEMO_RUNTIME_DIR = DEMO_SOURCE_DIR / "runtime"

REQUIRED = ["product_id", "name", "category", "year", "parts_count", "image_filename", "data_origin"]
EXPECTED_ORIGIN = "original_synthetic_demo"

# Fictional root-theme grouping of the demo categories (demo-only, not Rebrickable).
ROOT_THEME = {
    "Vehicles": "Wheels & Machines", "Transport": "Wheels & Machines",
    "Construction": "Wheels & Machines", "Rescue": "Wheels & Machines",
    "Space": "Exploration", "Ocean": "Exploration", "Nature": "Exploration",
    "Fantasy": "Fantasy & Creatures", "Creatures": "Fantasy & Creatures",
}
IMG_URL_PROVENANCE = "local:original-generated-demo-artwork/"


class DemoIngestError(RuntimeError):
    pass


def assert_isolated(runtime_dir: Path) -> Path:
    """Refuse any runtime directory that could touch the personal catalogue."""
    runtime = Path(runtime_dir).resolve()
    personal = Path(paths.DATA_DIR).resolve()
    if runtime == personal:
        raise DemoIngestError(f"Refusing to use {runtime}: that is the personal data directory.")
    for name in ("brickwise.db", "embeddings.npy", "embedding_ids.json"):
        if (runtime / name).resolve() == (personal / name).resolve():
            raise DemoIngestError(f"Refusing to use {runtime}: it would share {name} with personal data.")
    return runtime


def load_demo_rows(source_dir: Path = DEMO_SOURCE_DIR) -> list[dict]:
    """Read and validate products.csv, adapting it to the internal product contract."""
    path = Path(source_dir) / "products.csv"
    with open(path, newline="", encoding="utf-8") as f:
        raw = list(csv.DictReader(f))
    if not raw:
        raise DemoIngestError(f"{path} has no rows")
    missing = [c for c in REQUIRED if c not in raw[0]]
    if missing:
        raise DemoIngestError(f"{path} is missing columns: {missing}")
    rows, seen = [], set()
    for r in raw:
        pid = r["product_id"].strip()
        if pid in seen:
            raise DemoIngestError(f"duplicate product_id {pid}")
        seen.add(pid)
        if r["data_origin"] != EXPECTED_ORIGIN:
            raise DemoIngestError(f"{pid}: data_origin {r['data_origin']!r} is not {EXPECTED_ORIGIN!r}")
        category = r["category"].strip()
        if category not in ROOT_THEME:
            raise DemoIngestError(f"{pid}: no root-theme mapping for category {category!r}")
        image_file = Path(r["image_filename"]).name  # "images/bw-001.jpg" -> "bw-001.jpg"
        rows.append({
            "set_num": pid,                      # product_id -> set_num (original IDs preserved)
            "name": r["name"].strip(),
            "year": int(r["year"]),
            "theme_id": None,
            "theme": category,                   # category -> theme
            "root_theme": ROOT_THEME[category],
            "num_parts": int(r["parts_count"]),  # parts_count -> num_parts
            "img_url": IMG_URL_PROVENANCE + image_file,
            "image_file": image_file,            # image_filename -> image_file
        })
    return rows


def ingest_demo(source_dir: Path = DEMO_SOURCE_DIR, runtime_dir: Path = DEMO_RUNTIME_DIR,
                build_embeddings: bool = True, encoder=None, verbose: bool = True) -> dict:
    source_dir, runtime = Path(source_dir), assert_isolated(runtime_dir)
    rows = load_demo_rows(source_dir)
    src_images = source_dir / "images"
    missing = [r["image_file"] for r in rows if not (src_images / r["image_file"]).exists()]
    if missing:
        raise DemoIngestError(
            f"Missing demo images in {src_images}: {missing}. "
            "Generate them with `python -m brickwise.data.demo_artwork`.")
    img_dir = runtime / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for r in rows:
        shutil.copyfile(src_images / r["image_file"], img_dir / r["image_file"])
    db_path = runtime / "brickwise.db"
    con = products_db.connect(db_path)
    try:
        products_db.write_products(con, rows)  # upsert; any existing demo feedback is preserved
    finally:
        con.close()
    report = {"products": len(rows), "runtime_dir": str(runtime), "embeddings": None}
    if build_embeddings:
        report["embeddings"] = emb.build_embeddings(
            db_path=db_path, images_dir=img_dir, emb_path=runtime / "embeddings.npy",
            ids_path=runtime / "embedding_ids.json", encoder=encoder, verbose=verbose)
        ids = set(emb.load_cache(runtime / "embeddings.npy", runtime / "embedding_ids.json")[1])
        expected = {r["set_num"] for r in rows}
        if ids != expected:
            raise DemoIngestError(f"Embedding IDs do not match product IDs: {sorted(ids ^ expected)}")
    return report


def main() -> None:
    print(ingest_demo())


if __name__ == "__main__":
    main()
