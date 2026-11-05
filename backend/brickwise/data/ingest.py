"""Brickwise data ingestion: Rebrickable sets -> data/brickwise.db + data/images/*.jpg.

Usage (from backend/):  python -m brickwise.data.ingest --limit 800 [--offline-sample] [--seed 42]

Licensing / attribution
-----------------------
* Set and theme metadata come from the Rebrickable database downloads
  (https://rebrickable.com/downloads/). Rebrickable's licence/terms for the CSVs and for
  the images on its CDN have NOT been verified by this project: read them yourself and
  comply before using or sharing any of this data. Credit Rebrickable.com.
* Set images are fetched from the Rebrickable CDN (img_url) to your own machine for local
  use. They are not redistributed with the repo (data/ is gitignored) and must not be
  committed or republished. The photographs belong to their respective rights holders.
* LEGO(R) is a trademark of the LEGO Group, which does not sponsor, authorise or
  endorse this project. Brickwise is not affiliated with the LEGO Group.
* REBRICKABLE_API_KEY is not used by this script (no API fallback is implemented).
* --offline-sample generates clearly labelled synthetic placeholder images (no network).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

from . import products as P

BASE_URL = "https://cdn.rebrickable.com/media/downloads/"
USER_AGENT = "Brickwise/0.1 (educational)"
MAX_SIDE = 512
MIN_PARTS = 10
PREFERRED_YEAR = 2000
MIN_THEME_SETS = 5          # roots with fewer candidates are ignored
MAX_THEMES = 18             # keep the N largest root themes so each has enough sets to learn from
MAX_THEME_SHARE = 0.075     # cap per root theme as share of limit (60 sets at limit 800)
EXCLUDED_ROOTS = {"gear", "books", "supplemental", "service packs", "samples",
                  "promotional", "bulk bricks", "non-lego", "other", "system",
                  "universal building set", "lego brand store", "educational and dacta",
                  "seasonal", "hobby sets", "editions", "make & create", "xtra"}


# ---------------------------------------------------------------- paths
def data_dir() -> Path:
    env = os.environ.get("BRICKWISE_DATA_DIR")
    from .. import paths
    return Path(env) if env else paths.DATA_DIR


# ---------------------------------------------------------------- network
def fetch_bytes(url: str, timeout: int = 60, retries: int = 4) -> bytes:
    """GET with retries + exponential backoff. Tests monkeypatch this."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            if getattr(e, "code", None) in (403, 404, 410):
                break
            time.sleep(min(0.5 * 2 ** attempt, 8))
    raise RuntimeError(f"fetch failed for {url}: {last}")


def download_raw(raw_dir: Path, name: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    data = fetch_bytes(BASE_URL + name)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def read_csv_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- cleaning
def build_theme_index(theme_rows: list[dict]) -> dict[int, dict]:
    by_id = {}
    for r in theme_rows:
        try:
            tid = int(r["id"])
        except (KeyError, ValueError):
            continue
        pid = r.get("parent_id") or ""
        by_id[tid] = {"name": (r.get("name") or "").strip(),
                      "parent": int(pid) if pid.strip().isdigit() else None}
    return by_id


def root_theme(themes: dict[int, dict], tid: int) -> str | None:
    seen = set()
    cur = tid
    while cur in themes and cur not in seen:
        seen.add(cur)
        parent = themes[cur]["parent"]
        if parent is None or parent not in themes:
            return themes[cur]["name"]
        cur = parent
    return None


def clean_sets(set_rows: list[dict], themes: dict[int, dict]) -> tuple[list[dict], Counter]:
    """Validate rows; return (clean candidates, drop-reason counts)."""
    drops: Counter = Counter()
    out = []
    seen = set()
    for r in set_rows:
        sn = (r.get("set_num") or "").strip()
        name = (r.get("name") or "").strip()
        img = (r.get("img_url") or "").strip()
        if not sn:
            drops["missing set_num"] += 1; continue
        if sn in seen:
            drops["duplicate set_num"] += 1; continue
        seen.add(sn)
        if not name:
            drops["empty name"] += 1; continue
        try:
            parts = int(r.get("num_parts") or 0)
        except ValueError:
            parts = 0
        if parts <= 0:
            drops["zero/invalid parts"] += 1; continue
        if parts < MIN_PARTS:
            drops[f"num_parts < {MIN_PARTS}"] += 1; continue
        if not img.startswith("http"):
            drops["missing img_url"] += 1; continue
        try:
            tid = int(r["theme_id"])
        except (KeyError, ValueError, TypeError):
            drops["bad theme_id"] += 1; continue
        if tid not in themes:
            drops["unknown theme"] += 1; continue
        root = root_theme(themes, tid)
        if not root:
            drops["unresolvable root theme"] += 1; continue
        if root.lower() in EXCLUDED_ROOTS:
            drops[f"excluded theme ({root})"] += 1; continue
        try:
            year = int(r.get("year") or 0) or None
        except ValueError:
            year = None
        out.append({"set_num": sn, "name": name, "year": year, "theme_id": tid,
                    "theme": themes[tid]["name"], "root_theme": root,
                    "num_parts": parts, "img_url": img,
                    "image_file": f"{sn}.jpg"})
    return out, drops


# ---------------------------------------------------------------- selection
def _rank(seed: int, set_num: str) -> str:
    return hashlib.sha256(f"{seed}:{set_num}".encode()).hexdigest()


def select_sets(cands: list[dict], limit: int, seed: int = 42,
                exclude: set[str] | None = None) -> list[dict]:
    """Deterministic, theme-diverse selection (water-filling with per-theme cap)."""
    exclude = exclude or set()
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        if c["set_num"] not in exclude:
            groups[c["root_theme"]].append(c)
    for k in list(groups):
        if len(groups[k]) < MIN_THEME_SETS:
            del groups[k]
        else:  # modern sets first, then stable hash order
            groups[k].sort(key=lambda c: ((c["year"] or 0) < PREFERRED_YEAR,
                                          _rank(seed, c["set_num"])))
    if len(groups) > MAX_THEMES:
        keep = sorted(groups, key=lambda t: (-len(groups[t]), t))[:MAX_THEMES]
        groups = {k: groups[k] for k in keep}
    if not groups:
        return []
    # cap per theme, relaxed only if too few themes could otherwise reach `limit`
    cap = max(1, math.ceil(MAX_THEME_SHARE * limit), math.ceil(limit / len(groups)))
    # largest level L<=cap with sum(min(len, L)) <= limit
    level = 0
    for L in range(1, cap + 1):
        if sum(min(len(g), L) for g in groups.values()) <= limit:
            level = L
        else:
            break
    level = max(level, 1)
    chosen: dict[str, list[dict]] = {k: g[:level] for k, g in groups.items()}
    total = sum(len(v) for v in chosen.values())
    # distribute remainder one at a time, round-robin over themes, respecting cap
    while total < limit:
        progressed = False
        for k in sorted(groups, key=lambda t: (len(chosen[t]), t)):
            if total >= limit:
                break
            n = len(chosen[k])
            if n < cap and n < len(groups[k]):
                chosen[k].append(groups[k][n]); total += 1; progressed = True
        if not progressed:
            break
    sel = [c for k in sorted(chosen) for c in chosen[k]]
    return sorted(sel, key=lambda c: c["set_num"])


# ---------------------------------------------------------------- images
def process_image(raw: bytes, dest: Path) -> tuple[int, int]:
    """Verify with Pillow, convert to RGB JPEG max MAX_SIDE px, write atomically."""
    with Image.open(io.BytesIO(raw)) as im:
        im.verify()
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        im.save(tmp, format="JPEG", quality=88)
        tmp.replace(dest)
        return im.size


def image_ok(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:  # noqa: BLE001
        return False


def _fetch_one(row: dict, images_dir: Path) -> tuple[str, str | None]:
    dest = images_dir / row["image_file"]
    if image_ok(dest):
        return row["set_num"], None
    try:
        process_image(fetch_bytes(row["img_url"]), dest)
        return row["set_num"], None
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        return row["set_num"], f"{type(e).__name__}: {str(e)[:120]}"


def download_images(rows: list[dict], images_dir: Path, workers: int = 8) -> dict[str, str]:
    """Download images concurrently; return {set_num: error} for failures."""
    images_dir.mkdir(parents=True, exist_ok=True)
    fails = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for sn, err in ex.map(lambda r: _fetch_one(r, images_dir), rows):
            if err:
                fails[sn] = err
    return fails


# ---------------------------------------------------------------- offline sample
SAMPLE_THEMES = {"Star Wars": (200, 60, 60), "City": (60, 120, 220),
                 "Technic": (60, 160, 90), "Creator": (230, 170, 40)}


def make_offline_sample(images_dir: Path, per_theme: int = 6) -> list[dict]:
    images_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    n = 0
    for ti, (theme, base) in enumerate(SAMPLE_THEMES.items(), start=1):
        for j in range(per_theme):
            n += 1
            sn = f"SAMPLE{n:03d}-1"
            shade = tuple(min(255, c + 12 * j) for c in base)
            im = Image.new("RGB", (320, 240), shade)
            d = ImageDraw.Draw(im)
            for k in range(j + 2):  # themed "brick" blocks so CLIP-like models see variation
                d.rectangle([30 + 40 * k, 150 - 12 * k, 70 + 40 * k, 200], fill=(255, 255, 255), outline=(0, 0, 0))
            d.text((10, 10), "SYNTHETIC PLACEHOLDER", fill=(255, 255, 255))
            d.text((10, 28), f"{theme} #{j + 1}", fill=(255, 255, 255))
            im.save(images_dir / f"{sn}.jpg", "JPEG", quality=85)
            rows.append({"set_num": sn, "name": f"Sample {theme} Set {j + 1}",
                         "year": 2015 + j, "theme_id": 1000 + ti, "theme": theme,
                         "root_theme": theme, "num_parts": 50 + 25 * j + ti,
                         "img_url": f"synthetic://{sn}", "image_file": f"{sn}.jpg"})
    return rows


# ---------------------------------------------------------------- orchestration
def run(limit: int = 800, seed: int = 42, offline_sample: bool = False,
        workers: int = 8, ddir: Path | None = None) -> dict:
    ddir = Path(ddir) if ddir else data_dir()
    images_dir = ddir / "images"
    db_path = ddir / "brickwise.db"
    ddir.mkdir(parents=True, exist_ok=True)
    report: dict = {"mode": "offline-sample" if offline_sample else "rebrickable",
                    "seed": seed, "limit": limit, "attribution":
                    "Data: Rebrickable.com. LEGO(R) is a trademark of the LEGO Group, not affiliated."}
    if offline_sample:
        final = make_offline_sample(images_dir)
        report.update(raw_sets=0, clean_candidates=len(final), dropped={}, image_failures={})
    else:
        raw_dir = ddir / "raw"
        sets = read_csv_gz(download_raw(raw_dir, "sets.csv.gz"))
        themes = build_theme_index(read_csv_gz(download_raw(raw_dir, "themes.csv.gz")))
        cands, drops = clean_sets(sets, themes)
        report.update(raw_sets=len(sets), clean_candidates=len(cands))
        failed: dict[str, str] = {}
        final: list[dict] = []
        for _ in range(8):  # top up from the pool when images fail
            sel = select_sets(cands, limit, seed, exclude=set(failed))
            new_fails = download_images(sel, images_dir, workers)
            failed.update(new_fails)
            final = [r for r in sel if r["set_num"] not in failed]
            if not new_fails:
                break
        for _e in failed.values():
            drops["image download/verify failed"] += 1
        report.update(dropped=dict(drops.most_common()), image_failures=failed)
    con = P.connect(db_path)
    try:
        P.write_products(con, final)
    finally:
        con.close()
    keep_files = {r["image_file"] for r in final}   # prune orphan images from earlier runs
    for f in images_dir.glob("*.jpg"):
        if f.name not in keep_files:
            f.unlink()
    by_root = Counter(r["root_theme"] for r in final)
    report.update(
        products=len(final), images=sum(1 for r in final if image_ok(images_dir / r["image_file"])),
        root_themes=len(by_root), per_root_theme=dict(by_root.most_common()),
        themes=len({r["theme"] for r in final}),
        year_range=[min((r["year"] or 0) for r in final), max((r["year"] or 0) for r in final)] if final else None,
        db_path=str(db_path), images_dir=str(images_dir))
    (ddir / "ingest_report.json").write_text(json.dumps(report, indent=2))
    return report


def print_report(rep: dict) -> None:
    print(f"== Brickwise ingest ({rep['mode']}) ==")
    print(f"raw sets: {rep['raw_sets']}  clean candidates: {rep['clean_candidates']}")
    print(f"products: {rep['products']}  images ok: {rep['images']}  "
          f"root themes: {rep['root_themes']}  leaf themes: {rep['themes']}  years: {rep['year_range']}")
    print("sets per root theme:", ", ".join(f"{k}={v}" for k, v in rep["per_root_theme"].items()))
    if rep["dropped"]:
        print("dropped rows:")
        for k, v in rep["dropped"].items():
            print(f"  {v:>6}  {k}")
    print(f"report: {Path(rep['db_path']).parent / 'ingest_report.json'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=800)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--offline-sample", action="store_true",
                    help="no network: synthetic placeholder sets/images")
    a = ap.parse_args(argv)
    rep = run(a.limit, a.seed, a.offline_sample, a.workers)
    print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
