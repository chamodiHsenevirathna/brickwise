"""Filesystem locations shared by all Brickwise modules."""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("BRICKWISE_DATA_DIR", ROOT / "data"))
IMAGES_DIR = DATA_DIR / "images"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "brickwise.db"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"
EMBEDDING_IDS_PATH = DATA_DIR / "embedding_ids.json"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
