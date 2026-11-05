import pytest

from tests.api.conftest import BrokenProvider, rate


def test_preferences_empty(client):
    j = client.get("/api/preferences").json()
    assert (j["likes"], j["passes"], j["total_rated"], j["remaining"]) == (0, 0, 0, 12)
    assert j["top_themes"] == [] and j["avg_parts_liked"] is None and j["avg_parts_passed"] is None
    assert j["model"]["ready"] is False and j["model"]["min_likes"] == 3


def test_preferences_math(client):
    # themes by index%4: 0 SW(100 parts),1 City(200),2 Technic(300),3 Friends(400),4 SW(500),5 City(600)
    # likes: idx 0 (100), 4 (500), 1 (200) ; passes: idx 5 (600), 2 (300), 8 (900 SW)
    for i, r in [(0, 1), (4, 1), (1, 1), (5, 0), (2, 0), (8, 0)]:
        assert rate(client, f"{1000 + i}-1", r).status_code == 201
    j = client.get("/api/preferences").json()
    assert (j["likes"], j["passes"], j["total_rated"], j["remaining"]) == (3, 3, 6, 6)
    assert j["avg_parts_liked"] == pytest.approx((100 + 500 + 200) / 3, abs=0.01)
    assert j["avg_parts_passed"] == pytest.approx((600 + 300 + 900) / 3, abs=0.01)
    themes = {t["theme"]: t for t in j["top_themes"]}
    assert themes["Star Wars"] == {"theme": "Star Wars", "likes": 2, "passes": 1, "like_rate": pytest.approx(2 / 3, abs=1e-3)}
    assert themes["City"]["likes"] == 1 and themes["City"]["passes"] == 1 and themes["City"]["like_rate"] == 0.5
    assert themes["Technic"]["like_rate"] == 0.0
    assert j["top_themes"][0]["theme"] == "Star Wars"
    assert j["model"]["ready"] is True and j["model"]["likes"] == 3 and "training" in j["model"]


def test_preferences_model_unavailable(make_client):
    c = make_client(BrokenProvider("no embeddings"))
    rate(c, "1000-1", 1)
    j = c.get("/api/preferences").json()
    assert j["model"] == {"ready": False, "reason": "no embeddings"}
    assert j["likes"] == 1


def test_works_without_embeddings_real_provider(make_client, data_dir):
    """Default provider with no embeddings file: core endpoints work, recs unavailable."""
    c = make_client()  # no override -> LazyRecommender on empty tmp dir
    assert c.get("/api/health").json() == {"status": "ok", "products": 12, "embeddings": 0, "faiss": False}
    assert c.get("/api/products/next").status_code == 200
    assert rate(c, "1000-1", 1).status_code == 201
    assert c.get("/api/preferences").json()["model"]["ready"] is False
    j = c.get("/api/recommendations").json()
    assert j["status"] == "unavailable" and j["items"] == [] and j["message"]
    assert c.get("/api/evaluation").json()["sufficient"] is False
    sim = c.post("/api/evaluation/simulate").json()
    assert sim["simulated"] is True and sim["sufficient"] is False
