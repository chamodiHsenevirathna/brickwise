from brickwise.api.recommender import StaticProvider
from tests.api.conftest import BrokenProvider, rate, rate_many


def test_insufficient_logreg(client, products):
    rate_many(client, 2, 1, products)
    r = client.get("/api/recommendations")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "insufficient_feedback" and j["items"] == []
    assert (j["likes"], j["passes"], j["min_likes"], j["min_passes"]) == (2, 1, 3, 3)
    assert j["method"] == "logreg" and j["message"]


def test_insufficient_similarity_no_likes(client):
    j = client.get("/api/recommendations?method=similarity").json()
    assert j["status"] == "insufficient_feedback" and j["method"] == "similarity"


def test_ok_shape_and_filtering(client, products):
    rate_many(client, 3, 3, products)
    j = client.get("/api/recommendations?k=4").json()
    assert j["status"] == "ok" and len(j["items"]) == 4
    rated = {p["set_num"] for p in products[:6]}
    for it in j["items"]:
        assert it["product"]["set_num"] not in rated
        assert set(it) == {"product", "score", "explanation", "similar_to"}
        assert it["product"]["image_url"].startswith("/images/")
        assert len(it["similar_to"]) == 3
        assert it["similar_to"][0]["product"]["name"].startswith("Set ")
        assert it["similar_to"][0]["similarity"] == 0.9
    assert len({it["product"]["set_num"] for it in j["items"]}) == 4


def test_similarity_method_with_one_like(client):
    rate(client, "1000-1", 1)
    j = client.get("/api/recommendations?method=similarity&k=3").json()
    assert j["status"] == "ok" and len(j["items"]) == 3 and j["method"] == "similarity"


def test_updates_as_feedback_arrives(client, products):
    rate_many(client, 3, 3, products)
    first = [i["product"]["set_num"] for i in client.get("/api/recommendations?k=12").json()["items"]]
    rate(client, first[0], 1)
    second = [i["product"]["set_num"] for i in client.get("/api/recommendations?k=12").json()["items"]]
    assert first[0] not in second and len(second) == len(first) - 1
    client.post("/api/feedback/undo")
    assert first[0] in [i["product"]["set_num"] for i in client.get("/api/recommendations?k=12").json()["items"]]


def test_rated_items_never_returned_even_if_service_misbehaves(make_client, fake, products):
    orig = fake.recommend

    def bad(fb, k=5, method="logreg"):
        out = orig(fb, k, method)
        return out + [{"set_num": s, "score": 0.99, "method": method, "explanation": "x", "similar_to": []} for s in fb] + out[:1]

    fake.recommend = bad
    c = make_client(StaticProvider(fake))
    rate_many(c, 3, 3, products)
    items = c.get("/api/recommendations?k=5").json()["items"]
    ids = [i["product"]["set_num"] for i in items]
    assert not set(ids) & {p["set_num"] for p in products[:6]}
    assert len(ids) == len(set(ids))


def test_unknown_service_ids_skipped(make_client, fake, products):
    orig = fake.recommend
    fake.recommend = lambda fb, k=5, method="logreg": [
        {"set_num": "ghost-1", "score": 1.0, "method": method, "explanation": "", "similar_to": []}
    ] + orig(fb, k, method)
    c = make_client(StaticProvider(fake))
    rate_many(c, 3, 3, products)
    ids = [i["product"]["set_num"] for i in c.get("/api/recommendations?k=3").json()["items"]]
    assert "ghost-1" not in ids and len(ids) == 3


def test_unavailable(make_client):
    c = make_client(BrokenProvider("Embeddings not found"))
    j = c.get("/api/recommendations").json()
    assert j["status"] == "unavailable" and j["message"] == "Embeddings not found" and j["items"] == []


def test_service_crash_does_not_500(make_client, fake):
    def boom(*a, **k):
        raise RuntimeError("kaput")
    fake.recommend = boom
    c = make_client(StaticProvider(fake))
    r = c.get("/api/recommendations")
    assert r.status_code == 200 and r.json()["status"] == "unavailable"


def test_bad_params(client):
    assert client.get("/api/recommendations?method=magic").status_code == 422
    assert client.get("/api/recommendations?k=0").status_code == 422


def test_evaluation_and_simulate(client, products):
    j = client.get("/api/evaluation").json()
    assert j["simulated"] is False and j["sufficient"] is False
    rate_many(client, 6, 6, products)
    j = client.get("/api/evaluation").json()
    assert j["sufficient"] is True and j["winner"] == "logreg"
    s = client.post("/api/evaluation/simulate").json()
    assert s["simulated"] is True


def test_explanation_ids_are_replaced_with_names(client, products):
    rate_many(client, 3, 3, products)
    items = client.get("/api/recommendations?k=4").json()["items"]
    liked_ids = {it["similar_to"][0]["product"]["set_num"] for it in items}
    for it in items:
        assert it["explanation"].startswith("Looks like ")
        # raw id alone is not acceptable; it must be "<Name> (<id>)" when the liked set is a known product
        for sn in liked_ids:
            if sn in it["explanation"]:
                assert f"({sn})" in it["explanation"]
