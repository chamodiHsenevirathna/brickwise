"""Integration with the real RecommenderService on tiny synthetic embeddings (no CLIP)."""
import json

import numpy as np
import pytest

pytest.importorskip("brickwise.ml.service")
from fastapi.testclient import TestClient  # noqa: E402

from brickwise.api.main import create_app  # noqa: E402
from tests.api.conftest import make_products, rate, seed_products  # noqa: E402


@pytest.fixture
def real_client(data_dir):
    prods = seed_products(data_dir, 24)
    rng = np.random.default_rng(0)
    # two clusters: even index vs odd index
    centers = np.eye(16, dtype=np.float32)[:2] * 3
    emb = np.stack([centers[i % 2] + rng.normal(0, 0.3, 16) for i in range(24)]).astype(np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    np.save(data_dir / "embeddings.npy", emb)
    (data_dir / "embedding_ids.json").write_text(json.dumps([p["set_num"] for p in prods]))
    return TestClient(create_app(data_dir)), prods


def test_real_service_end_to_end(real_client):
    c, prods = real_client
    ids = [p["set_num"] for p in prods]
    assert c.get("/api/health").json()["embeddings"] == 24
    assert c.get("/api/recommendations").json()["status"] == "insufficient_feedback"
    evens, odds = ids[0::2], ids[1::2]
    for s in evens[:4]:
        rate(c, s, 1)
    for s in odds[:4]:
        rate(c, s, 0)
    rated = set(evens[:4]) | set(odds[:4])
    for method in ("logreg", "similarity"):
        j = c.get(f"/api/recommendations?k=6&method={method}").json()
        assert j["status"] == "ok", j
        got = [i["product"]["set_num"] for i in j["items"]]
        assert len(got) == 6 and not set(got) & rated and len(set(got)) == 6
        assert all(i["similar_to"] and i["similar_to"][0]["product"]["set_num"] in evens[:4] for i in j["items"])
    top = c.get("/api/recommendations?k=3").json()["items"]
    assert all(int(i["product"]["set_num"].split("-")[0]) % 2 == 0 for i in top)  # even-indexed cluster (1000+even)
    m = c.get("/api/preferences").json()["model"]
    assert m["ready"] is True and m["likes"] == 4
    ev = c.get("/api/evaluation").json()
    assert ev["simulated"] is False
    sim = c.post("/api/evaluation/simulate").json()
    assert sim["simulated"] is True
