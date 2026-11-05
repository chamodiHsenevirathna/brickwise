import json

import numpy as np
import pytest

from brickwise.ml import evaluation as ev
from brickwise.ml.embeddings import build_embeddings, l2_normalise, load_cache
from brickwise.ml.service import InsufficientFeedback, RecommenderService

THEMES = ["Star Wars", "City", "Technic", "Friends"]


def make_data(per=20, dim=32, seed=0):
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(len(THEMES), dim))
    emb, ids, products = [], [], []
    for t, c in enumerate(centers):
        for i in range(per):
            emb.append(c + 0.3 * rng.normal(size=dim))
            sid = f"{t}-{i}"
            ids.append(sid)
            products.append({"set_num": sid, "root_theme": THEMES[t], "theme": THEMES[t]})
    return l2_normalise(np.array(emb)), ids, products


@pytest.fixture(params=[True, False], ids=["faiss", "numpy"])
def svc(request):
    emb, ids, _ = make_data()
    s = RecommenderService.from_arrays(emb, ids, use_faiss=request.param)
    if request.param:
        pytest.importorskip("faiss")
    return s


def fb_for(theme_idx, n=4, other=(1, 2), per=20):
    fb = {f"{theme_idx}-{i}": 1 for i in range(n)}
    for o in other:
        for i in range(2):
            fb[f"{o}-{i}"] = 0
    return fb


def test_precision_at_k_edges():
    assert ev.precision_at_k([1, 0, 1, 1], 2) == 0.5
    assert ev.precision_at_k([1, 1], 5) == 1.0  # k larger than list
    assert ev.precision_at_k([], 5) == 0.0
    assert ev.precision_at_k([1, 1], 0) == 0.0
    assert ev.precision_at_k([0, 0, 0], 3) == 0.0


def test_backend_flag():
    emb, ids, _ = make_data()
    assert RecommenderService.from_arrays(emb, ids, use_faiss=False).backend == "numpy"
    assert RecommenderService.from_arrays(emb, ids).backend in ("faiss", "numpy")


def test_insufficient_feedback(svc):
    st = svc.status({"0-0": 1, "1-0": 0})
    assert not st["ready"] and st["reason"] and st["likes"] == 1 and st["passes"] == 1
    with pytest.raises(InsufficientFeedback):
        svc.recommend({"0-0": 1, "1-0": 0}, method="logreg")
    with pytest.raises(InsufficientFeedback):
        svc.fit({})
    with pytest.raises(ValueError):
        svc.similar_to_liked({"1-0": 0})
    assert issubclass(InsufficientFeedback, ValueError)


def test_recommend_exclusion_duplicates_and_quality(svc):
    fb = fb_for(0)
    for method in ("logreg", "similarity"):
        recs = svc.recommend(fb, k=10, method=method)
        got = [r["set_num"] for r in recs]
        assert len(got) == 10 == len(set(got))
        assert not set(got) & set(fb)
        assert all(g.startswith("0-") for g in got)  # same cluster as likes
        for r in recs:
            assert 0 <= r["score"] <= 1 and r["method"] == method
            assert r["explanation"] and 1 <= len(r["similar_to"]) <= 3
            assert all(s["set_num"] in fb and fb[s["set_num"]] == 1 for s in r["similar_to"])
            assert str(r["similar_to"][0]["set_num"]) in r["explanation"]


def test_explanation_is_truthful(svc):
    r = svc.recommend(fb_for(0), k=1)[0]
    assert f"{round(r['score'] * 100)}%" in r["explanation"]
    assert f"{r['similar_to'][0]['similarity']:.2f}" in r["explanation"]


def test_retraining_changes_output(svc):
    before = svc.recommend(fb_for(0), k=5)
    after = svc.recommend(fb_for(3, other=(0, 1)), k=5)
    assert {r["set_num"] for r in before} != {r["set_num"] for r in after}
    assert all(r["set_num"].startswith("3-") for r in after)
    st = svc.fit(fb_for(0))
    assert st["ready"] and st["trained_on"] == 8 and 0 <= st["train_accuracy"] <= 1


def test_all_rated_returns_empty():
    emb, ids, _ = make_data(per=2)
    s = RecommenderService.from_arrays(emb, ids)
    fb = {i: (1 if n < 4 else 0) for n, i in enumerate(ids)}
    assert s.recommend(fb) == [] and s.similar_to_liked(fb) == []


def test_unknown_ids_ignored(svc):
    fb = fb_for(0)
    fb["nope"] = 1
    assert svc.status(fb)["likes"] == 4


def test_faiss_numpy_parity():
    pytest.importorskip("faiss")
    emb, ids, _ = make_data()
    a = RecommenderService.from_arrays(emb, ids, use_faiss=True)
    b = RecommenderService.from_arrays(emb, ids, use_faiss=False)
    assert a.backend == "faiss" and b.backend == "numpy"
    fb = fb_for(2, other=(0, 1))
    for m in ("logreg", "similarity"):
        ra, rb = a.recommend(fb, 8, m), b.recommend(fb, 8, m)
        assert [r["set_num"] for r in ra] == [r["set_num"] for r in rb]
        np.testing.assert_allclose([r["score"] for r in ra], [r["score"] for r in rb], atol=1e-4)


def test_evaluate_insufficient(svc):
    rep = svc.evaluate({"0-0": 1, "1-0": 0})
    assert rep["sufficient"] is False and rep["reason"] and rep["simulated"] is False
    assert rep["winner"] is None and rep["methods"] == {}
    skew = {f"0-{i}": 1 for i in range(9)} | {"1-0": 0}
    assert svc.evaluate(skew)["sufficient"] is False


def test_evaluate_sufficient(svc):
    fb = {f"0-{i}": 1 for i in range(16)} | {f"1-{i}": 0 for i in range(16)}
    rep = svc.evaluate(fb, n_repeats=10)
    assert rep["sufficient"] and rep["simulated"] is False and rep["k"] == 5
    assert rep["n_ratings"] == 32 and rep["n_splits"] == 10 and rep["base_rate"] == 0.5
    assert set(rep["methods"]) == {"logreg", "similarity", "random"}
    assert rep["methods"]["logreg"]["precision_at_k"] > 0.9
    assert rep["methods"]["similarity"]["precision_at_k"] > rep["methods"]["random"]["precision_at_k"]
    assert rep["winner"] in ("logreg", "similarity") or rep["winner"] is None
    json.dumps(rep)


def test_simulate_flagged(svc):
    _, _, products = make_data()
    rep = svc.simulate(products, seed=1, n_users=3, n_rated=40, n_repeats=5)
    assert rep["simulated"] is True and rep["sufficient"] and "SIMULATED" in rep["protocol"]
    assert rep["methods"]["logreg"]["precision_at_k"] >= rep["methods"]["random"]["precision_at_k"]
    json.dumps(rep)


def test_simulate_without_labels_is_insufficient(svc):
    rep = svc.simulate([])
    assert rep["simulated"] is True and rep["sufficient"] is False and rep["reason"]


def test_embedding_cache_incremental(tmp_path):
    import sqlite3
    from PIL import Image
    from brickwise import paths
    db = tmp_path / "b.db"
    img = tmp_path / "images"
    img.mkdir()
    con = sqlite3.connect(db)
    con.executescript(paths.SCHEMA_PATH.read_text())
    for n in ("a-1", "b-1"):
        Image.new("RGB", (8, 8)).save(img / f"{n}.jpg")
        con.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)", (n, n, 2020, 1, "T", "T", 10, "u", f"{n}.jpg"))
    con.commit()

    class Fake:
        calls = []
        def encode_paths(self, ps):
            self.calls.append([p.name for p in ps])
            return l2_normalise(np.random.default_rng(len(self.calls)).normal(size=(len(ps), 512)))

    e, i = tmp_path / "e.npy", tmp_path / "i.json"
    f = Fake()
    r = build_embeddings(db, img, e, i, encoder=f, verbose=False)
    assert r["new"] == 2 and r["total"] == 2
    r = build_embeddings(db, img, e, i, encoder=f, verbose=False)
    assert r["new"] == 0 and len(f.calls) == 1
    Image.new("RGB", (8, 8)).save(img / "c-1.jpg")
    con.execute("INSERT INTO products VALUES ('c-1','c',2020,1,'T','T',10,'u','c-1.jpg')")
    con.commit()
    r = build_embeddings(db, img, e, i, encoder=f, verbose=False)
    assert r["new"] == 1 and f.calls[-1] == ["c-1.jpg"]
    emb, ids = load_cache(e, i)
    assert emb.shape == (3, 512) and emb.dtype == np.float32 and len(ids) == 3
    np.testing.assert_allclose(np.linalg.norm(emb, axis=1), 1, atol=1e-5)
    assert not list(tmp_path.glob("*.tmp"))
