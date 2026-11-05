from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brickwise.api.main import create_app, get_recommender
from brickwise.api.recommender import InsufficientFeedback, RecommenderUnavailable, StaticProvider

THEMES = ["Star Wars", "City", "Technic", "Friends"]


def make_products(n: int = 12) -> list[dict]:
    return [
        {
            "set_num": f"{1000 + i}-1", "name": f"Set {i}", "year": 2000 + i,
            "theme_id": i % 4, "theme": THEMES[i % 4], "root_theme": THEMES[i % 4],
            "num_parts": 100 * (i + 1), "img_url": f"http://x/{i}.jpg", "image_file": f"{1000 + i}-1.jpg",
        }
        for i in range(n)
    ]


def seed_products(data_dir: Path, n: int = 12) -> list[dict]:
    prods = make_products(n)
    app = create_app(data_dir)  # applies schema
    conn = sqlite3.connect(app.state.db_path)
    conn.executemany(
        "INSERT OR IGNORE INTO products VALUES (:set_num,:name,:year,:theme_id,:theme,:root_theme,:num_parts,:img_url,:image_file)",
        prods,
    )
    conn.commit()
    conn.close()
    return prods


class FakeRecommender:
    """Implements the RecommenderService contract over a fixed id list."""

    backend = "numpy"

    def __init__(self, ids, min_likes=3, min_passes=3):
        self._ids = list(ids)
        self.min_likes, self.min_passes = min_likes, min_passes
        self.calls = []

    def ids(self):
        return list(self._ids)

    def _counts(self, fb):
        likes = sum(1 for v in fb.values() if v == 1)
        return likes, len(fb) - likes

    def status(self, fb):
        likes, passes = self._counts(fb)
        ready = likes >= self.min_likes and passes >= self.min_passes
        return {"ready": ready, "likes": likes, "passes": passes, "min_likes": self.min_likes,
                "min_passes": self.min_passes, "reason": None if ready else "need more ratings",
                "backend": self.backend}

    def recommend(self, fb, k=5, method="logreg"):
        self.calls.append((dict(fb), k, method))
        likes, passes = self._counts(fb)
        if method == "logreg" and not self.status(fb)["ready"]:
            raise InsufficientFeedback("Need at least 3 likes and 3 passes")
        if method == "similarity" and likes == 0:
            raise InsufficientFeedback("Like something first")
        liked = [s for s, v in fb.items() if v == 1][:3]
        out = []
        for i, sid in enumerate(s for s in self._ids if s not in fb):
            out.append({
                "set_num": sid, "score": round(1 - i * 0.01, 4), "method": method,
                "explanation": f"Looks like {liked[0]}" if liked else "n/a",
                "similar_to": [{"set_num": l, "similarity": 0.9} for l in liked],
            })
        return out[:k]

    def evaluate(self, fb, k=5, **kw):
        likes, passes = self._counts(fb)
        ok = len(fb) >= 10
        return {"simulated": False, "k": k, "sufficient": ok, "reason": None if ok else "need >= 10 ratings",
                "n_ratings": len(fb), "n_likes": likes, "n_passes": passes, "n_splits": 3 if ok else 0,
                "protocol": "fake", "methods": {"logreg": {"precision_at_k": 0.5, "std": 0.1}} if ok else {},
                "winner": "logreg" if ok else None, "base_rate": 0.5}

    def simulate(self, products, k=5, **kw):
        return {"simulated": True, "k": k, "sufficient": True, "reason": None, "n_ratings": len(products),
                "n_likes": 1, "n_passes": 1, "n_splits": 2, "protocol": "fake-sim",
                "methods": {"random": {"precision_at_k": 0.2, "std": 0.0}}, "winner": "random", "base_rate": 0.2}


class BrokenProvider:
    def __init__(self, msg="Embeddings not found"):
        self.msg = msg

    def get(self):
        raise RecommenderUnavailable(self.msg)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BRICKWISE_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def products(data_dir):
    return seed_products(data_dir)


@pytest.fixture
def fake(products):
    return FakeRecommender([p["set_num"] for p in products])


@pytest.fixture
def make_client(data_dir, products):
    """Factory: new app instance on the same DB each call (simulates restart)."""
    def _make(provider=None):
        app = create_app(data_dir)
        if provider is not None:
            app.dependency_overrides[get_recommender] = lambda: provider
        return TestClient(app)
    return _make


@pytest.fixture
def client(make_client, fake):
    return make_client(StaticProvider(fake))


def rate(client, set_num, rating):
    return client.post("/api/feedback", json={"set_num": set_num, "rating": rating})


def rate_many(client, likes, passes, products):
    ids = [p["set_num"] for p in products]
    for s in ids[:likes]:
        assert rate(client, s, 1).status_code == 201
    for s in ids[likes:likes + passes]:
        assert rate(client, s, 0).status_code == 201
