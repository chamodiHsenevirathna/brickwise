"""Independent demo mode: catalogue, images, isolation, feedback, recommendations, reset."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from brickwise import paths
from brickwise.api import demo as demo_api
from brickwise.api.demo import EXAMPLE_HOLDOUT, create_demo_app, load_example_profile
from brickwise.api.main import create_app
from brickwise.data import demo_ingest
from brickwise.data.demo_ingest import DemoIngestError, assert_isolated, ingest_demo, load_demo_rows
from brickwise.ml.service import RecommenderService

SRC = demo_ingest.DEMO_SOURCE_DIR
IDS = [f"BW-{i:03d}" for i in range(1, 13)]


class FakeEncoder:
    """Deterministic stand-in for CLIP (no model download): one unit vector per image file name."""

    def encode_paths(self, paths_):
        out = []
        for p in paths_:
            seed = int(hashlib.sha256(Path(p).name.encode()).hexdigest()[:8], 16)
            v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
            out.append(v / np.linalg.norm(v))
        return np.vstack(out)


@pytest.fixture(scope="module")
def runtime(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("demo_runtime")
    ingest_demo(SRC, d, encoder=FakeEncoder(), verbose=False)
    return d


@pytest.fixture()
def client(runtime, tmp_path):
    # fresh copy of the runtime dir per test so feedback never leaks between tests
    import shutil
    d = tmp_path / "rt"
    shutil.copytree(runtime, d)
    with TestClient(create_demo_app(d, SRC)) as c:
        c.data_dir = d
        yield c


def rate(c, pid, r):
    return c.post("/api/feedback", json={"set_num": pid, "rating": r})


# ---------------- catalogue + images ----------------
def test_catalogue_loads_and_maps_fields():
    rows = load_demo_rows(SRC)
    assert [r["set_num"] for r in sorted(rows, key=lambda r: r["set_num"])] == IDS
    r1 = next(r for r in rows if r["set_num"] == "BW-001")
    assert (r1["name"], r1["theme"], r1["num_parts"], r1["image_file"]) == ("Ridgeback Rally Car", "Vehicles", 186, "bw-001.jpg")
    assert r1["root_theme"] == "Wheels & Machines"
    assert all("rebrickable" not in (r["img_url"] + r["name"]).lower() for r in rows)


def test_products_api_preserves_ids_and_image_paths(client):
    items = client.get("/api/products/next?limit=50").json()["items"]
    assert sorted(i["set_num"] for i in items) == IDS
    for i in items:
        assert i["image_url"] == f"/images/{i['set_num'].lower()}.jpg"
        res = client.get(i["image_url"])
        assert res.status_code == 200 and res.headers["content-type"] == "image/jpeg"


def test_source_images_exist_and_are_valid():
    from PIL import Image
    for pid in IDS:
        with Image.open(SRC / "images" / f"{pid.lower()}.jpg") as im:
            assert im.size == (512, 512)


def test_embedding_ids_match_product_ids(runtime):
    ids = __import__("json").loads((runtime / "embedding_ids.json").read_text())
    assert sorted(ids) == IDS
    assert np.load(runtime / "embeddings.npy").shape == (12, 512)


# ---------------- isolation ----------------
def test_refuses_personal_data_directory():
    with pytest.raises(DemoIngestError):
        assert_isolated(paths.DATA_DIR)
    with pytest.raises(DemoIngestError):
        create_demo_app(paths.DATA_DIR)
    with pytest.raises(DemoIngestError):
        ingest_demo(SRC, paths.DATA_DIR, build_embeddings=False)


def test_default_runtime_is_a_subdirectory_with_its_own_files():
    rt = demo_ingest.DEMO_RUNTIME_DIR.resolve()
    assert rt != Path(paths.DATA_DIR).resolve()
    assert (rt / "brickwise.db") != paths.DB_PATH and (rt / "embeddings.npy") != paths.EMBEDDINGS_PATH


def test_demo_and_personal_feedback_are_isolated(runtime, tmp_path):
    import shutil
    d = tmp_path / "rt"
    shutil.copytree(runtime, d)
    personal_dir = tmp_path / "personal"
    personal = create_app(personal_dir)
    with sqlite3.connect(personal.state.db_path) as c:
        c.execute("INSERT INTO products VALUES ('P-1','Personal',2000,1,'City','City',10,'x','p.jpg')")
        c.execute("INSERT INTO feedback (set_num, rating) VALUES ('P-1', 1)")
    with TestClient(create_demo_app(d, SRC)) as dc, TestClient(personal) as pc:
        assert dc.post("/api/demo/example-profile").status_code == 200
        assert dc.post("/api/demo/reset").status_code == 200
        assert dc.delete("/api/feedback").status_code == 204
        assert pc.get("/api/feedback").json()["likes"] == 1          # personal rating untouched
        assert dc.get("/api/feedback").json()["items"] == []
        assert pc.post("/api/feedback", json={"set_num": "BW-001", "rating": 1}).status_code == 404
    with sqlite3.connect(personal.state.db_path) as c:
        assert c.execute("SELECT set_num, rating FROM feedback").fetchall() == [("P-1", 1)]
        assert "demo_meta" not in {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
        assert c.execute("SELECT COUNT(*) FROM products WHERE set_num LIKE 'BW-%'").fetchone()[0] == 0


# ---------------- feedback + undo ----------------
def test_feedback_creation_duplicates_and_undo(client):
    assert rate(client, "BW-001", 1).status_code == 201
    assert rate(client, "BW-001", 0).status_code == 409
    assert rate(client, "BW-002", 0).status_code == 201
    assert rate(client, "NOPE", 1).status_code == 404
    undone = client.post("/api/feedback/undo").json()
    assert undone["undone"]["set_num"] == "BW-002" and undone["remaining"] == 11
    fb = client.get("/api/feedback").json()
    assert [i["set_num"] for i in fb["items"]] == ["BW-001"]


def test_fresh_demo_starts_with_no_feedback(client):
    assert client.get("/api/feedback").json()["items"] == []
    info = client.get("/api/demo/info").json()
    assert info["profile_mode"] == "fresh" and info["banner"].startswith("Independent demo catalogue")


# ---------------- example profile + reset ----------------
def test_example_profile_seeding_is_labelled_and_leaves_candidates(client):
    res = client.post("/api/demo/example-profile").json()
    assert res["seeded"] == 10 and res["held_out"] == list(EXAMPLE_HOLDOUT)
    assert "synthetic" in res["warning"].lower()
    fb = client.get("/api/feedback").json()
    assert fb["likes"] == 6 and fb["passes"] == 4
    assert not {i["set_num"] for i in fb["items"]} & set(EXAMPLE_HOLDOUT)
    info = client.get("/api/demo/info").json()
    assert info["profile_mode"] == "example" and "synthetic" in info["example_profile"]["warning"].lower()
    assert client.post("/api/demo/example-profile").json()["seeded"] == 10   # idempotent replace
    assert client.get("/api/feedback").json()["likes"] == 6


def test_example_profile_matches_source_file():
    prof = load_example_profile(SRC)
    assert len(prof["ratings"]) == 12 and sum(r for _, r in prof["ratings"]) == 7


def test_reset_clears_demo_only(client):
    client.post("/api/demo/example-profile")
    assert client.post("/api/demo/reset").json()["profile_mode"] == "fresh"
    assert client.get("/api/feedback").json()["items"] == []
    assert client.get("/api/demo/info").json()["profile_mode"] == "fresh"
    assert client.get("/api/products/next?limit=50").json()["remaining"] == 12


# ---------------- recommendations ----------------
def test_insufficient_feedback_is_reported_not_faked(client):
    rate(client, "BW-001", 1); rate(client, "BW-002", 1); rate(client, "BW-004", 0); rate(client, "BW-007", 0)
    d = client.get("/api/recommendations?method=logreg").json()
    assert d["status"] == "insufficient_feedback" and d["items"] == []
    assert (d["min_likes"], d["min_passes"]) == (3, 3)  # production thresholds unchanged


def test_recommendations_come_from_the_real_model(client, runtime):
    client.post("/api/demo/example-profile")
    d = client.get("/api/recommendations?method=logreg&k=5").json()
    assert d["status"] == "ok" and {i["product"]["set_num"] for i in d["items"]} == set(EXAMPLE_HOLDOUT)
    fb = {i["set_num"]: i["rating"] for i in client.get("/api/feedback").json()["items"]}
    svc = RecommenderService(runtime / "embeddings.npy", runtime / "embedding_ids.json")
    expected = {r["set_num"]: r["score"] for r in svc.recommend(fb, k=5)}
    for item in d["items"]:
        assert item["score"] == pytest.approx(expected[item["product"]["set_num"]])
        assert item["explanation"] and 0.0 <= item["score"] <= 1.0
    s = client.get("/api/recommendations?method=similarity").json()
    assert s["status"] == "ok" and len(s["items"]) == 2


def test_evaluation_on_example_profile_runs_and_small_data_is_reported(client):
    client.post("/api/demo/example-profile")
    ev = client.get("/api/evaluation").json()
    assert ev["sufficient"] is True and ev["n_ratings"] == 10
    client.post("/api/demo/reset")
    assert client.get("/api/evaluation").json()["sufficient"] is False


def test_missing_embeddings_degrade_gracefully(runtime, tmp_path):
    import shutil
    d = tmp_path / "rt"
    shutil.copytree(runtime, d)
    (d / "embeddings.npy").unlink()
    with TestClient(create_demo_app(d, SRC)) as c:
        c.post("/api/demo/example-profile")
        r = c.get("/api/recommendations").json()
        assert r["status"] == "unavailable" and "Embeddings not found" in r["message"]
        assert c.get("/api/evaluation").json()["sufficient"] is False
        assert c.get("/api/products/next").status_code == 200   # browsing still works
