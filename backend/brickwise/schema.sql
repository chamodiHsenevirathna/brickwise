-- Shared SQLite schema. DB file: <repo>/data/brickwise.db
-- products: written ONLY by brickwise.data (ingestion). Read-only for everyone else.
CREATE TABLE IF NOT EXISTS products (
  set_num      TEXT PRIMARY KEY,          -- e.g. "75192-1"
  name         TEXT NOT NULL,
  year         INTEGER,
  theme_id     INTEGER,
  theme        TEXT NOT NULL,             -- leaf theme name, e.g. "Star Wars"
  root_theme   TEXT NOT NULL,             -- top-level ancestor theme name
  num_parts    INTEGER,
  img_url      TEXT NOT NULL,             -- remote Rebrickable CDN url (provenance)
  image_file   TEXT NOT NULL              -- file name inside data/images/, e.g. "75192-1.jpg"
);
-- feedback: written ONLY by brickwise.api. One row per product (UNIQUE) => duplicate prevention.
CREATE TABLE IF NOT EXISTS feedback (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  set_num    TEXT NOT NULL UNIQUE REFERENCES products(set_num),
  rating     INTEGER NOT NULL CHECK (rating IN (0,1)),   -- 1 = like, 0 = pass
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
