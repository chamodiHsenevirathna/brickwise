"""Real-catalogue demo: a small, read-only selection of the user's *local* catalogue.

Everything here is local-only. It reads the personal catalogue (``data/brickwise.db``
``products`` table, ``data/embeddings.npy`` + ``embedding_ids.json``, ``data/images/``) strictly
read-only and writes only inside ``data/demo-real/`` (git-ignored via ``data/*``)::

    python -m brickwise.data.demo_real propose   # pick 16 products, write a contact sheet (NOT frozen)
    python -m brickwise.data.demo_real freeze    # after human review: freeze the proposal
    python -m brickwise.data.demo_real build     # demo DB + embeddings sliced from the existing ones

Guarantees:
* The personal DB is opened with ``mode=ro`` and a SQLite authorizer that *denies any read of the
  ``feedback`` table*, so personal ratings can neither influence selection nor leak.
* Embeddings are sliced out of the existing cache. CLIP is never loaded or run.
* Product photographs are never copied; the demo API serves them read-only from ``data/images/``
  (see ``brickwise.api.demo``).
* The selection, the example profile and the contact sheet contain Rebrickable metadata/photos, so
  they live only under ``data/demo-real/`` and must never be committed.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

from .. import paths
from ..ml import embeddings as emb
from . import products as products_db
from .demo_ingest import assert_isolated

REAL_RUNTIME_DIR = paths.ROOT / "data" / "demo-real"
N_PRODUCTS = 16
EXCLUDED_ROOTS = ("Duplo", "Town")
# Stated rule for the simulated example profile (NOT derived from any personal rating).
LIKE_ROOTS = ("City", "Technic", "Space", "Racers", "Star Wars", "Ninjago")
HOLDOUT_LIKES = 2
HOLDOUT_PASSES = 2
PROFILE_ID = "simulated-vehicles-space-fan"
PROFILE_WARNING = (
    "Simulated ratings generated from a stated rule, not collected from a real person and not "
    "evidence of recommendation quality."
)
SELECTED_COLUMNS = ["set_num", "name", "year", "theme", "root_theme", "num_parts", "image_file"]


class DemoRealError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- read-only access
def _deny_feedback(action, arg1, arg2, dbname, source):
    if action == sqlite3.SQLITE_READ and (arg1 or "").lower() == "feedback":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def open_personal_catalogue(personal_dir: Path) -> sqlite3.Connection:
    """Read-only connection to the personal DB that cannot read the ``feedback`` table."""
    db = Path(personal_dir) / "brickwise.db"
    if not db.exists():
        raise DemoRealError(
            f"No local catalogue at {db}. Build it first (see README: Getting started), "
            "or use the fictional demo.")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.set_authorizer(_deny_feedback)
    return con


def load_catalogue(personal_dir: Path) -> dict[str, dict]:
    con = open_personal_catalogue(personal_dir)
    try:
        return {r["set_num"]: dict(r) for r in con.execute("SELECT * FROM products")}
    finally:
        con.close()


def load_personal_embeddings(personal_dir: Path):
    d = Path(personal_dir)
    ids = json.loads((d / "embedding_ids.json").read_text())
    arr = np.load(d / "embeddings.npy", mmap_mode="r")
    if arr.shape[0] != len(ids):
        raise DemoRealError("Personal embeddings and ids are out of sync.")
    return arr, ids


# ----------------------------------------------------------------------------- selection
def propose_selection(personal_dir: Path, n: int = N_PRODUCTS, excluded_roots=EXCLUDED_ROOTS) -> dict:
    """Deterministic: one product per root theme, mid-to-large sets, as visually distinct as possible.

    Candidates per root theme are sets at or above that theme's median piece count (excluding the
    top 5% outliers). Greedy farthest-point sampling on the existing CLIP embeddings then picks one
    candidate per theme, starting from the most "typical" candidate and repeatedly adding the
    candidate (from a not-yet-used theme) with the largest minimum cosine distance to those chosen.
    """
    cat = load_catalogue(personal_dir)
    emb_arr, ids = load_personal_embeddings(personal_dir)
    index_of = {s: i for i, s in enumerate(ids)}
    roots = sorted({p["root_theme"] for p in cat.values()} - set(excluded_roots))
    if len(roots) < n:
        raise DemoRealError(f"Only {len(roots)} eligible root themes; need {n}.")
    cands: list[dict] = []
    for rt in roots:
        ps = sorted((p for p in cat.values() if p["root_theme"] == rt and p["set_num"] in index_of
                     and p["num_parts"] is not None), key=lambda p: (p["num_parts"], p["set_num"]))
        if not ps:
            continue
        parts = np.array([p["num_parts"] for p in ps])
        lo, hi = np.median(parts), np.percentile(parts, 95)
        pool = [p for p in ps if lo <= p["num_parts"] <= hi] or ps
        cands.extend(pool)
    X = np.asarray(emb_arr[[index_of[p["set_num"]] for p in cands]], dtype=np.float32)
    typical = int(np.argmax(X @ X.mean(axis=0)))
    chosen = [typical]
    used = {cands[typical]["root_theme"]}
    mind = 1.0 - X @ X[typical]
    while len(chosen) < n:
        order = np.argsort(-mind, kind="stable")
        pick = next((int(i) for i in order if cands[int(i)]["root_theme"] not in used), None)
        if pick is None:
            break
        chosen.append(pick)
        used.add(cands[pick]["root_theme"])
        mind = np.minimum(mind, 1.0 - X @ X[pick])
    if len(chosen) < n:
        raise DemoRealError(f"Could only select {len(chosen)} of {n} products.")
    products = sorted((cands[i] for i in chosen), key=lambda p: (p["root_theme"], p["set_num"]))
    return {
        "status": "proposed",
        "n": n,
        "excluded_roots": list(excluded_roots),
        "method": ("One product per root theme; sets at or above the theme's median piece count "
                   "(top 5% excluded); greedy farthest-point sampling on existing CLIP embeddings. "
                   "Personal ratings are never read."),
        "products": [{k: p[k] for k in SELECTED_COLUMNS} for p in products],
    }


def write_contact_sheet(selection: dict, personal_dir: Path, out: Path, cols: int = 4, cell: int = 300) -> Path:
    from PIL import Image, ImageDraw

    prods = selection["products"]
    rows = -(-len(prods) // cols)
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 62)), "white")
    d = ImageDraw.Draw(sheet)
    for i, p in enumerate(prods):
        x, y = (i % cols) * cell, (i // cols) * (cell + 62)
        with Image.open(Path(personal_dir) / "images" / p["image_file"]) as im:
            im = im.convert("RGB")
            im.thumbnail((cell - 10, cell - 10))
            sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        d.text((x + 6, y + cell + 2), f"{p['set_num']}  {p['name'][:34]}", fill="black")
        d.text((x + 6, y + cell + 18), f"{p['root_theme']} / {p['theme']}"[:44], fill="gray")
        d.text((x + 6, y + cell + 34), f"{p['num_parts']} pieces, {p['year']}", fill="gray")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def _paths(runtime: Path) -> dict[str, Path]:
    return {"proposed": runtime / "selection.proposed.json", "frozen": runtime / "selection.json",
            "sheet": runtime / "contact_sheet.png"}


def propose(personal_dir: Path = paths.DATA_DIR, runtime_dir: Path = REAL_RUNTIME_DIR) -> dict:
    runtime = assert_isolated(runtime_dir)
    sel = propose_selection(personal_dir)
    p = _paths(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    p["proposed"].write_text(json.dumps(sel, indent=2))
    write_contact_sheet(sel, personal_dir, p["sheet"])
    return {"proposed": str(p["proposed"]), "contact_sheet": str(p["sheet"]), "n": len(sel["products"])}


def freeze(runtime_dir: Path = REAL_RUNTIME_DIR, force: bool = False) -> Path:
    """Explicit human step: promote the reviewed proposal to the frozen selection."""
    runtime = assert_isolated(runtime_dir)
    p = _paths(runtime)
    if not p["proposed"].exists():
        raise DemoRealError("Nothing to freeze: run `propose` and review the contact sheet first.")
    if p["frozen"].exists() and not force:
        raise DemoRealError(f"{p['frozen']} already exists; pass --force to replace it.")
    sel = json.loads(p["proposed"].read_text())
    sel["status"] = "frozen"
    p["frozen"].write_text(json.dumps(sel, indent=2))
    return p["frozen"]


# ----------------------------------------------------------------------------- example profile
def make_example_profile(products: list[dict]) -> dict:
    """Simulated profile from a stated rule on root theme; independent of personal ratings."""
    ordered = sorted(products, key=lambda p: p["set_num"])
    ratings = [(p["set_num"], 1 if p["root_theme"] in LIKE_ROOTS else 0) for p in ordered]
    likes = [s for s, r in ratings if r == 1]
    passes = [s for s, r in ratings if r == 0]
    holdout = likes[:HOLDOUT_LIKES] + passes[:HOLDOUT_PASSES]
    seeded_likes, seeded_passes = len(likes) - HOLDOUT_LIKES, len(passes) - HOLDOUT_PASSES
    if seeded_likes < 4 or seeded_passes < 4 or seeded_likes + seeded_passes < 10:
        raise DemoRealError("Selection does not allow a valid example profile (need >=10 ratings, >=4 per class).")
    return {
        "profile_id": PROFILE_ID,
        "description": "Simulated fan of " + ", ".join(LIKE_ROOTS[:-1]) + " and " + LIKE_ROOTS[-1]
                       + " sets; every other theme is a Pass.",
        "warning": PROFILE_WARNING,
        "rule": {"like_root_themes": list(LIKE_ROOTS)},
        "ratings": [[s, r] for s, r in ratings],
        "holdout": holdout,
    }


# ----------------------------------------------------------------------------- build
def build_real_demo(personal_dir: Path = paths.DATA_DIR, runtime_dir: Path = REAL_RUNTIME_DIR) -> dict:
    runtime = assert_isolated(runtime_dir)
    if runtime == Path(personal_dir).resolve():
        raise DemoRealError("Refusing to build the demo inside the personal data directory.")
    frozen = _paths(runtime)["frozen"]
    if not frozen.exists():
        raise DemoRealError(
            f"Selection not frozen ({frozen} missing). Run `propose`, review the contact sheet, "
            "then `freeze`.")
    wanted = [p["set_num"] for p in json.loads(frozen.read_text())["products"]]
    cat = load_catalogue(personal_dir)
    emb_arr, ids = load_personal_embeddings(personal_dir)
    index_of = {s: i for i, s in enumerate(ids)}
    missing = [s for s in wanted if s not in cat or s not in index_of
               or not (Path(personal_dir) / "images" / cat[s]["image_file"]).is_file()]
    if missing:
        raise DemoRealError(f"Selected products missing from the local catalogue/embeddings/images: {missing}")
    rows = [cat[s] for s in wanted]                      # real records, unmodified
    runtime.mkdir(parents=True, exist_ok=True)
    con = products_db.connect(runtime / "brickwise.db")
    try:
        products_db.write_products(con, rows)            # upsert; existing demo feedback is preserved
    finally:
        con.close()
    sub = np.asarray(emb_arr[[index_of[s] for s in wanted]], dtype=np.float32)  # reused, not regenerated
    emb.save_cache(sub, wanted, runtime / "embeddings.npy", runtime / "embedding_ids.json")
    profile = make_example_profile(rows)
    (runtime / "example_profile.json").write_text(json.dumps(profile, indent=2))
    return {"products": len(rows), "runtime_dir": str(runtime), "embeddings_reused": len(wanted),
            "holdout": profile["holdout"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["propose", "freeze", "build"])
    ap.add_argument("--force", action="store_true", help="freeze: replace an existing frozen selection")
    args = ap.parse_args(argv)
    try:
        if args.command == "propose":
            print(propose())
            print("Review the contact sheet, then run `freeze`. Nothing is frozen yet.")
        elif args.command == "freeze":
            print("frozen:", freeze(force=args.force))
        else:
            print(build_real_demo())
    except DemoRealError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
