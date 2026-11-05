from tests.api.conftest import rate, rate_many


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "products": 12, "embeddings": 12, "faiss": False}


def test_next_unrated_only_and_deterministic(client):
    a = client.get("/api/products/next?limit=12").json()
    b = client.get("/api/products/next?limit=12").json()
    assert a == b
    assert a["total"] == 12 and a["remaining"] == 12 and len(a["items"]) == 12
    assert {i["set_num"] for i in a["items"]} == {f"{1000 + i}-1" for i in range(12)}
    first = a["items"][0]
    assert first["image_url"] == f"/images/{first['set_num']}.jpg"
    assert set(first) == {"set_num", "name", "year", "theme", "root_theme", "num_parts", "image_url"}
    rate(client, first["set_num"], 1)
    c = client.get("/api/products/next?limit=12").json()
    assert c["remaining"] == 11
    assert [i["set_num"] for i in c["items"]] == [i["set_num"] for i in a["items"][1:]]
    assert client.get("/api/products/next").json()["items"][0]["set_num"] == a["items"][1]["set_num"]


def test_next_limit_validation(client):
    assert client.get("/api/products/next?limit=0").status_code == 422


def test_post_feedback_shape_and_remaining(client):
    r = rate(client, "1000-1", 1)
    assert r.status_code == 201
    body = r.json()
    assert body["remaining"] == 11
    assert set(body["feedback"]) == {"id", "set_num", "rating", "created_at"}
    assert body["feedback"]["rating"] == 1 and body["feedback"]["set_num"] == "1000-1"
    assert rate(client, "1001-1", 0).json()["remaining"] == 10


def test_duplicate_409(client):
    assert rate(client, "1000-1", 1).status_code == 201
    assert rate(client, "1000-1", 0).status_code == 409
    assert rate(client, "1000-1", 1).status_code == 409
    assert client.get("/api/feedback").json()["likes"] == 1


def test_unknown_404(client):
    assert rate(client, "nope-1", 1).status_code == 404


def test_bad_rating_422(client):
    for bad in (2, -1, "like", None, 0.5):
        assert client.post("/api/feedback", json={"set_num": "1000-1", "rating": bad}).status_code == 422
    assert client.post("/api/feedback", json={"set_num": "1000-1"}).status_code == 422
    assert client.get("/api/feedback").json()["items"] == []


def test_list_feedback_with_products(client):
    rate(client, "1000-1", 1)
    rate(client, "1001-1", 0)
    j = client.get("/api/feedback").json()
    assert (j["likes"], j["passes"]) == (1, 1)
    assert [i["set_num"] for i in j["items"]] == ["1001-1", "1000-1"]
    assert j["items"][0]["product"]["name"] == "Set 1"


def test_undo_removes_most_recent_and_product_reappears(client):
    assert client.post("/api/feedback/undo").status_code == 404
    rate(client, "1000-1", 1)
    rate(client, "1001-1", 0)
    rate(client, "1002-1", 1)
    nxt_before = client.get("/api/products/next?limit=12").json()
    assert "1002-1" not in [i["set_num"] for i in nxt_before["items"]]
    r = client.post("/api/feedback/undo")
    assert r.status_code == 200
    assert r.json()["undone"]["set_num"] == "1002-1"
    assert r.json()["remaining"] == 10
    nxt = client.get("/api/products/next?limit=12").json()
    assert "1002-1" in [i["set_num"] for i in nxt["items"]]
    assert client.post("/api/feedback/undo").json()["undone"]["set_num"] == "1001-1"
    # undone item can be re-rated
    assert rate(client, "1001-1", 1).status_code == 201
    # most recent is by id, so the re-rated one is undone first
    assert client.post("/api/feedback/undo").json()["undone"]["set_num"] == "1001-1"


def test_undo_until_empty(client):
    rate(client, "1000-1", 1)
    assert client.post("/api/feedback/undo").status_code == 200
    assert client.post("/api/feedback/undo").status_code == 404
    assert client.get("/api/products/next").json()["remaining"] == 12


def test_reset(client, products):
    rate_many(client, 3, 3, products)
    assert client.delete("/api/feedback").status_code == 204
    assert client.get("/api/feedback").json() == {"items": [], "likes": 0, "passes": 0}
    assert client.get("/api/products/next").json()["remaining"] == 12
    assert rate(client, "1000-1", 1).status_code == 201


def test_persistence_across_app_restarts(make_client, fake):
    from brickwise.api.recommender import StaticProvider
    c1 = make_client(StaticProvider(fake))
    rate(c1, "1000-1", 1)
    rate(c1, "1001-1", 0)
    c1.close()
    c2 = make_client(StaticProvider(fake))
    j = c2.get("/api/feedback").json()
    assert {(i["set_num"], i["rating"]) for i in j["items"]} == {("1000-1", 1), ("1001-1", 0)}
    assert c2.get("/api/products/next").json()["remaining"] == 10
    assert rate(c2, "1000-1", 0).status_code == 409
    assert c2.post("/api/feedback/undo").json()["undone"]["set_num"] == "1001-1"
    c3 = make_client(StaticProvider(fake))
    assert c3.get("/api/feedback").json()["likes"] == 1 and c3.get("/api/feedback").json()["passes"] == 0


def test_images_mounted_and_cors(client, data_dir):
    (data_dir / "images" / "1000-1.jpg").write_bytes(b"\xff\xd8fake")
    assert client.get("/images/1000-1.jpg").content == b"\xff\xd8fake"
    assert client.get("/images/missing.jpg").status_code == 404
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
