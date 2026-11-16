"""Real-catalogue demo, tested on a FABRICATED local catalogue (no Rebrickable data in the repo)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from brickwise import paths
from brickwise.api import demo as demo_api
from brickwise.api.demo import create_default_app, create_demo_app
from brickwise.data import demo_real
from brickwise.data import products as products_db
from brickwise.data.demo_real import DemoRealError
from brickwise.ml import embeddings as emb_mod

LIKES = demo_real.LIKE_ROOTS
# 18 fabricated root themes: the 6 "like" rule themes, the 2 excluded ones, and 10 others
ROOTS = sorted(list(LIKES) + ["Duplo", "Town", "Alpha", "Bravo", "Charlie", "Delta", "Echo",
                              "Foxtrot", "Golf", "Hotel", "India", "Juliet"])


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def fingerprint(d: Path) -> dict:
    out = {p.relative_to(d).as_posix(): sha(p) for p in sorted(d.rglob("*")) if p.is_file()}
    return out


@pytest.fixture(scope="module")
def personal(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("personal")
    (d / "images").mkdir()
    rows, vecs, ids = [], [], []
    rng = np.random.default_rng(7)
    for ri, root in enumerate(ROOTS):
        centre = rng.normal(size=512)
        for k in range(8):
            sn = f"{ri:02d}{k:02d}-1"
            v = centre + 0.6 * rng.normal(size=512)
            vecs.append((v / np.linalg.norm(v)).astype(np.float32))
            ids.append(sn)
            Image.new("RGB", (40, 30), (ri * 12 % 255, k * 30 % 255, 90)).save(d / "images" / f"{sn}.jpg")
            rows.append({"set_num": sn, "name": f"Fab {root} {k}", "year": 2000 + k, "theme_id": ri,
                         "theme": f"{root} sub", "root_theme": root, "num_parts": 50 + 40 * k + ri,
                         "img_url": f"https://example.invalid/{sn}.jpg", "image_file": f"{sn}.jpg"})
    con = products_db.connect(d / "brickwise.db")
    products_db.write_products(con, rows)
    con.executemany("INSERT INTO feedback (set_num, rating) VALUES (?, ?)",
                    [(r["set_num"], i % 2) for i, r in enumerate(rows[:37])])   # "personal ratings"
    con.commit()
    con.close()
    emb_mod.save_cache(np.vstack(vecs), ids, d / "embeddings.npy", d / "embedding_ids.json")
    return d


@pytest.fixture()
def built(personal, tmp_path):
    runtime = tmp_path / "demo-real"
    demo_real.propose(personal, runtime)
    demo_real.freeze(runtime)
    demo_real.build_real_demo(personal, runtime)
    return runtime


@pytest.fixture()
def client(personal, built):
    with TestClient(create_demo_app(built, catalogue="real", images_dir=personal / "images")) as c:
        c.runtime = built
        yield c


# ---------------- read-only access + selection ----------------
def test_personal_feedback_table_is_unreadable_but_products_are(personal):
    con = demo_real.open_personal_catalogue(personal)
    assert con.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 18 * 8
    for sql in ("SELECT * FROM feedback", "SELECT COUNT(*) FROM feedback",
                "SELECT p.set_num FROM products p JOIN feedback f ON f.set_num = p.set_num"):
        with pytest.raises(sqlite3.DatabaseError):
            con.execute(sql).fetchall()
    with pytest.raises(sqlite3.OperationalError):          # and it is read-only
        con.execute("DELETE FROM products")
    con.close()


def test_selection_is_16_distinct_roots_deterministic_and_excludes_themes(personal):
    a, b = demo_real.propose_selection(personal), demo_real.propose_selection(personal)
    assert a == b and a["status"] == "proposed" and len(a["products"]) == 16
    roots = [p["root_theme"] for p in a["products"]]
    assert len(set(roots)) == 16 and not set(roots) & {"Duplo", "Town"}


def test_selection_ignores_personal_ratings(personal, tmp_path):
    other = tmp_path / "p2"
    import shutil
    shutil.copytree(personal, other)
    con = sqlite3.connect(other / "brickwise.db")
    con.execute("DELETE FROM feedback"); con.commit(); con.close()
    assert demo_real.propose_selection(personal) == demo_real.propose_selection(other)


def test_build_requires_a_frozen_selection(personal, tmp_path):
    rt = tmp_path / "rt"
    with pytest.raises(DemoRealError, match="not frozen"):
        demo_real.build_real_demo(personal, rt)
    demo_real.propose(personal, rt)                         # proposing alone does not unlock build
    with pytest.raises(DemoRealError, match="not frozen"):
        demo_real.build_real_demo(personal, rt)
    assert (rt / "contact_sheet.png").exists() and not (rt / "selection.json").exists()
    with pytest.raises(DemoRealError):
        demo_real.freeze(tmp_path / "empty")


def test_refuses_personal_directory_as_runtime(personal):
    with pytest.raises(RuntimeError, match="personal data directory"):
        demo_real.build_real_demo(personal, personal)
    with pytest.raises(RuntimeError):
        create_demo_app(personal, catalogue="real")


# ---------------- build: real records, reused embeddings, no mutation ----------------
def test_build_preserves_real_records_and_reuses_embeddings(personal, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("CLIP must not be loaded or run")
    monkeypatch.setattr(emb_mod, "ClipEncoder", boom)
    before = fingerprint(personal)
    rt = tmp_path / "rt"
    demo_real.propose(personal, rt); demo_real.freeze(rt)
    rep = demo_real.build_real_demo(personal, rt)
    assert rep["products"] == 16 and rep["embeddings_reused"] == 16
    assert fingerprint(personal) == before                  # personal DB, images, embeddings: byte-identical
    cat = demo_real.load_catalogue(personal)
    demo_rows = {r["set_num"]: dict(r) for r in products_db.connect(rt / "brickwise.db").execute("SELECT * FROM products")}
    assert len(demo_rows) == 16
    for sn, row in demo_rows.items():
        assert row == cat[sn]                               # name, set number, theme, parts etc. unchanged
        assert row["image_file"] == f"{sn}.jpg"
    emb, ids = emb_mod.load_cache(rt / "embeddings.npy", rt / "embedding_ids.json")
    p_emb, p_ids = demo_real.load_personal_embeddings(personal)
    assert sorted(ids) == sorted(demo_rows)
    for i, sn in enumerate(ids):
        assert np.array_equal(emb[i], np.asarray(p_emb[p_ids.index(sn)], dtype=np.float32))
    assert not list((rt).glob("**/*.jpg"))                  # photographs are never copied


def test_example_profile_is_rule_based_labelled_and_valid(built):
    prof = json.loads((built / "example_profile.json").read_text())
    assert "Simulated" in prof["warning"] and prof["rule"]["like_root_themes"] == list(LIKES)
    seeded = [(s, r) for s, r in prof["ratings"] if s not in prof["holdout"]]
    assert len(prof["ratings"]) == 16 and len(prof["holdout"]) == 4
    assert sum(r for _, r in seeded) >= 4 and sum(1 - r for _, r in seeded) >= 4 and len(seeded) >= 10


# ---------------- image route ----------------
def test_images_served_read_only_from_personal_dir(client, personal):
    items = client.get("/api/products/next?limit=50").json()["items"]
    assert len(items) == 16
    for it in items:
        assert it["image_url"] == f"/images/{it['set_num']}.jpg"
        r = client.get(it["image_url"])
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
        assert r.content == (personal / "images" / f"{it['set_num']}.jpg").read_bytes()


def test_image_route_rejects_unselected_traversal_and_writes(client, personal):
    selected = {i["set_num"] for i in client.get("/api/products/next?limit=50").json()["items"]}
    other = next(p.stem for p in (personal / "images").glob("*.jpg") if p.stem not in selected)
    assert client.get(f"/images/{other}.jpg").status_code == 404           # exists locally, not selected
    for bad in ("../brickwise.db", "..%2Fbrickwise.db", "%2e%2e/embeddings.npy", "nope.jpg", "brickwise.db"):
        assert client.get(f"/images/{bad}").status_code == 404, bad
    sn = sorted(selected)[0]
    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)(f"/images/{sn}.jpg").status_code == 405
    assert not (client.runtime / "images").exists() or not list((client.runtime / "images").glob("*"))


# ---------------- isolation + demo feedback ----------------
def test_demo_feedback_is_isolated_from_personal_ratings(client, personal):
    before = fingerprint(personal)
    assert client.get("/api/feedback").json()["items"] == []        # none of the 37 personal ratings appear
    sns = [i["set_num"] for i in client.get("/api/products/next?limit=50").json()["items"]]
    assert client.post("/api/feedback", json={"set_num": sns[0], "rating": 1}).status_code == 201
    assert client.post("/api/feedback", json={"set_num": sns[0], "rating": 0}).status_code == 409
    assert client.post("/api/feedback", json={"set_num": sns[1], "rating": 0}).status_code == 201
    assert client.post("/api/feedback/undo").json()["undone"]["set_num"] == sns[1]
    assert [i["set_num"] for i in client.get("/api/feedback").json()["items"]] == [sns[0]]
    client.post("/api/demo/example-profile"); client.post("/api/demo/reset"); client.delete("/api/feedback")
    raw = sqlite3.connect(personal / "brickwise.db")
    assert raw.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 37
    raw.close()
    assert fingerprint(personal) == before
    assert Path(client.app.state.db_path) != personal / "brickwise.db"


def test_info_is_labelled_for_the_real_catalogue(client):
    info = client.get("/api/demo/info").json()
    assert info["catalogue"] == "real" and info["product_count"] == 16
    assert "Real LEGO" in info["banner"] and "Simulated" in info["banner"]
    assert "Fictional" not in info["banner"] and "Rebrickable" in info["footer"]
    assert "Simulated" in info["example_profile"]["warning"]


def test_example_profile_seed_recommend_evaluate_reset(client):
    res = client.post("/api/demo/example-profile").json()
    assert res["profile_mode"] == "example" and len(res["held_out"]) == 4 and res["seeded"] == 12
    fb = client.get("/api/feedback").json()
    assert not {i["set_num"] for i in fb["items"]} & set(res["held_out"])
    rec = client.get("/api/recommendations?method=logreg&k=5").json()
    assert rec["status"] == "ok" and {i["product"]["set_num"] for i in rec["items"]} == set(res["held_out"])
    assert (rec["min_likes"], rec["min_passes"]) == (3, 3)
    assert client.get("/api/recommendations?method=similarity").json()["status"] == "ok"
    ev = client.get("/api/evaluation").json()
    assert ev["sufficient"] is True and ev["n_ratings"] == 12
    assert client.post("/api/demo/reset").json()["profile_mode"] == "fresh"
    assert client.get("/api/feedback").json()["items"] == []
    assert client.get("/api/recommendations").json()["status"] == "insufficient_feedback"


def test_real_mode_fails_clearly_when_not_built(tmp_path):
    with pytest.raises(RuntimeError, match="not built"):
        create_demo_app(tmp_path / "nothing", catalogue="real")


# ---------------- fictional mode keeps working without local data ----------------
def test_default_app_falls_back_to_fictional_without_real_catalogue(tmp_path, monkeypatch):
    monkeypatch.setenv("BRICKWISE_DEMO_REAL_DIR", str(tmp_path / "missing"))
    monkeypatch.delenv("BRICKWISE_DEMO_CATALOGUE", raising=False)
    monkeypatch.setattr(demo_api, "DEMO_RUNTIME_DIR", tmp_path / "fict-runtime")
    app = create_default_app()
    assert app.state.demo_catalogue == "fictional"


def test_default_app_uses_real_when_built_and_explicit_override(built, tmp_path, monkeypatch):
    monkeypatch.setenv("BRICKWISE_DEMO_REAL_DIR", str(built))
    monkeypatch.delenv("BRICKWISE_DEMO_CATALOGUE", raising=False)
    assert create_default_app().state.demo_catalogue == "real"
    monkeypatch.setenv("BRICKWISE_DEMO_CATALOGUE", "fictional")
    monkeypatch.setattr(demo_api, "DEMO_RUNTIME_DIR", tmp_path / "fict-runtime")
    assert create_default_app().state.demo_catalogue == "fictional"
    monkeypatch.setenv("BRICKWISE_DEMO_CATALOGUE", "bogus")
    with pytest.raises(ValueError):
        create_default_app()
