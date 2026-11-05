"""Brickwise FastAPI app.

Run (from ``backend/``)::

    ../.venv/bin/uvicorn brickwise.api.main:app --port 8000
    # dev with reload:
    ../.venv/bin/uvicorn brickwise.api.main:app --port 8000 --reload

Env: ``BRICKWISE_DATA_DIR`` overrides the data directory (DB, images, embeddings).
Interactive docs at http://localhost:8000/docs. Recommendations are recomputed
from the current feedback on every request (the model retrains from scratch,
which is cheap), so the model always reflects the latest ratings.
"""
from __future__ import annotations

import re
import os
import random
import sqlite3
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from brickwise import paths
from brickwise.api import db
from brickwise.api.recommender import (
    LazyRecommender,
    RecommenderUnavailable,
    is_insufficient,
)

SHUFFLE_SEED = 20240607
DEFAULT_MIN = 3


class FeedbackIn(BaseModel):
    set_num: str
    rating: Literal[0, 1]


# ---- dependencies ---------------------------------------------------------
def get_conn(request: Request):
    conn = db.connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_recommender(request: Request):
    """Returns a provider with ``.get()`` (raises RecommenderUnavailable). Override in tests."""
    return request.app.state.recommender


# ---- helpers --------------------------------------------------------------
def _feedback_map(conn) -> dict[str, int]:
    return {r["set_num"]: r["rating"] for r in conn.execute("SELECT set_num, rating FROM feedback")}


def _remaining(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM products WHERE set_num NOT IN (SELECT set_num FROM feedback)"
    ).fetchone()[0]


def _products_by_id(conn, ids) -> dict[str, dict]:
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {}
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        q = ",".join("?" * len(chunk))
        for r in conn.execute(f"SELECT * FROM products WHERE set_num IN ({q})", chunk):
            out[r["set_num"]] = db.product_from_row(r)
    return out


def _counts(fb: dict[str, int]) -> tuple[int, int]:
    likes = sum(1 for v in fb.values() if v == 1)
    return likes, len(fb) - likes


def _model_status(provider, fb) -> dict:
    try:
        svc = provider.get()
        st = dict(svc.status(fb))
        st["training"] = "retrained from scratch on current feedback at every recommendation request"
        return st
    except RecommenderUnavailable as exc:
        return {"ready": False, "reason": str(exc)}
    except Exception as exc:  # never crash the profile page
        return {"ready": False, "reason": f"Model status unavailable: {exc}"}


def _empty_report(message: str, simulated: bool, k: int) -> dict:
    return {
        "simulated": simulated, "k": k, "sufficient": False, "reason": message,
        "n_ratings": 0, "n_likes": 0, "n_passes": 0, "n_splits": 0, "protocol": "",
        "methods": {}, "winner": None, "base_rate": 0.0,
    }


# ---- app factory ----------------------------------------------------------
def create_app(data_dir: Optional[Path] = None) -> FastAPI:
    env = os.environ.get("BRICKWISE_DATA_DIR")
    data_dir = Path(data_dir) if data_dir else (Path(env) if env else paths.DATA_DIR)
    images_dir = data_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Brickwise API", version="1.0")
    app.state.data_dir = data_dir
    app.state.db_path = data_dir / "brickwise.db"
    app.state.recommender = LazyRecommender(data_dir / "embeddings.npy", data_dir / "embedding_ids.json")
    db.init_db(app.state.db_path)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/images", StaticFiles(directory=str(images_dir)), name="images")

    @app.get("/api/health")
    def health(conn=Depends(get_conn), provider=Depends(get_recommender)):
        n = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        emb, faiss = 0, False
        try:
            svc = provider.get()
            emb = len(svc.ids())
            faiss = getattr(svc, "backend", None) == "faiss" or svc.status({}).get("backend") == "faiss"
        except Exception:
            pass
        return {"status": "ok", "products": n, "embeddings": emb, "faiss": bool(faiss)}

    @app.get("/api/products/next")
    def products_next(limit: int = Query(1, ge=1, le=50), conn=Depends(get_conn)):
        # Deterministic: fixed-seed shuffle of ALL products (sorted by id), then drop the
        # rated ones, so rating/undoing never reorders the remaining items.
        allrows = conn.execute("SELECT * FROM products ORDER BY set_num").fetchall()
        random.Random(SHUFFLE_SEED).shuffle(allrows)
        rated = {r[0] for r in conn.execute("SELECT set_num FROM feedback")}
        rows = [r for r in allrows if r["set_num"] not in rated]
        total = len(allrows)
        return {"items": [db.product_from_row(r) for r in rows[:limit]], "remaining": len(rows), "total": total}

    @app.post("/api/feedback", status_code=201)
    def post_feedback(body: FeedbackIn, conn=Depends(get_conn)):
        if conn.execute("SELECT 1 FROM products WHERE set_num=?", (body.set_num,)).fetchone() is None:
            raise HTTPException(404, f"Unknown product {body.set_num}")
        try:
            cur = conn.execute("INSERT INTO feedback (set_num, rating) VALUES (?, ?)", (body.set_num, body.rating))
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(409, f"Product {body.set_num} already rated")
        row = conn.execute("SELECT * FROM feedback WHERE id=?", (cur.lastrowid,)).fetchone()
        return {"feedback": db.feedback_from_row(row), "remaining": _remaining(conn)}

    @app.post("/api/feedback/undo")
    def undo(conn=Depends(get_conn)):
        row = conn.execute("SELECT * FROM feedback ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            raise HTTPException(404, "Nothing to undo")
        conn.execute("DELETE FROM feedback WHERE id=?", (row["id"],))
        conn.commit()
        return {"undone": db.feedback_from_row(row), "remaining": _remaining(conn)}

    @app.get("/api/feedback")
    def list_feedback(conn=Depends(get_conn)):
        rows = conn.execute(
            "SELECT f.id, f.set_num, f.rating, f.created_at, p.* FROM feedback f "
            "JOIN products p ON p.set_num = f.set_num ORDER BY f.id DESC"
        ).fetchall()
        items = [{**db.feedback_from_row(r), "product": db.product_from_row(r)} for r in rows]
        likes = sum(1 for i in items if i["rating"] == 1)
        return {"items": items, "likes": likes, "passes": len(items) - likes}

    @app.delete("/api/feedback", status_code=204)
    def reset(conn=Depends(get_conn)):
        conn.execute("DELETE FROM feedback")
        conn.commit()
        return Response(status_code=204)

    @app.get("/api/preferences")
    def preferences(conn=Depends(get_conn), provider=Depends(get_recommender)):
        fb = _feedback_map(conn)
        likes, passes = _counts(fb)
        themes = conn.execute(
            "SELECT p.theme AS theme, SUM(f.rating) AS likes, SUM(1 - f.rating) AS passes "
            "FROM feedback f JOIN products p ON p.set_num = f.set_num GROUP BY p.theme"
        ).fetchall()
        top = [
            {"theme": t["theme"], "likes": t["likes"], "passes": t["passes"],
             "like_rate": round(t["likes"] / (t["likes"] + t["passes"]), 4)}
            for t in themes
        ]
        top.sort(key=lambda t: (-t["likes"], -t["like_rate"], t["passes"], t["theme"]))

        def avg(rating):
            v = conn.execute(
                "SELECT AVG(p.num_parts) FROM feedback f JOIN products p ON p.set_num=f.set_num "
                "WHERE f.rating=? AND p.num_parts IS NOT NULL", (rating,)
            ).fetchone()[0]
            return None if v is None else round(v, 2)

        return {
            "likes": likes, "passes": passes, "total_rated": likes + passes,
            "remaining": _remaining(conn), "top_themes": top[:10],
            "avg_parts_liked": avg(1), "avg_parts_passed": avg(0),
            "model": _model_status(provider, fb),
        }

    @app.get("/api/recommendations")
    def recommendations(
        k: int = Query(5, ge=1, le=50),
        method: Literal["logreg", "similarity"] = "logreg",
        conn=Depends(get_conn),
        provider=Depends(get_recommender),
    ):
        fb = _feedback_map(conn)
        likes, passes = _counts(fb)
        base = {"method": method, "min_likes": DEFAULT_MIN, "min_passes": DEFAULT_MIN,
                "likes": likes, "passes": passes, "items": []}
        try:
            svc = provider.get()
        except RecommenderUnavailable as exc:
            return {**base, "status": "unavailable", "message": str(exc)}
        try:
            st = svc.status(fb)
            base["min_likes"] = st.get("min_likes", DEFAULT_MIN)
            base["min_passes"] = st.get("min_passes", DEFAULT_MIN)
        except Exception:
            pass
        try:
            raw = svc.recommend(fb, k=k, method=method)
        except Exception as exc:
            if is_insufficient(exc):
                return {**base, "status": "insufficient_feedback", "message": str(exc)}
            return {**base, "status": "unavailable", "message": f"Recommender error: {exc}"}
        # Defensive: never return a rated or duplicate item, whatever the service did.
        seen: set[str] = set()
        raw = [r for r in raw if r["set_num"] not in fb and not (r["set_num"] in seen or seen.add(r["set_num"]))]
        ids = [r["set_num"] for r in raw] + [s["set_num"] for r in raw for s in r.get("similar_to", [])]
        prods = _products_by_id(conn, ids)
        items = []
        for r in raw:
            if r["set_num"] not in prods:
                continue
            items.append({
                "product": prods[r["set_num"]],
                "score": float(r["score"]),
                "explanation": _humanise(r.get("explanation", ""), prods),
                "similar_to": [
                    {"product": prods[s["set_num"]], "similarity": float(s["similarity"])}
                    for s in r.get("similar_to", []) if s["set_num"] in prods
                ],
            })
        return {**base, "status": "ok", "message": f"Top {len(items)} picks ({method}).", "items": items}

    def _humanise(text: str, prods: dict) -> str:
        """Replace raw set ids in a service explanation with 'Name (id)'."""
        for sn in sorted(prods, key=len, reverse=True):
            text = re.sub(rf"(?<![\w-]){re.escape(sn)}(?![\w-])", f"{prods[sn]['name']} ({sn})", text)
        return text

    @app.get("/api/evaluation")
    def evaluation(k: int = Query(5, ge=1, le=50), conn=Depends(get_conn), provider=Depends(get_recommender)):
        try:
            svc = provider.get()
            return svc.evaluate(_feedback_map(conn), k=k)
        except RecommenderUnavailable as exc:
            return _empty_report(str(exc), False, k)
        except Exception as exc:
            return _empty_report(str(exc) if is_insufficient(exc) else f"Evaluation error: {exc}", False, k)

    @app.post("/api/evaluation/simulate")
    def simulate(k: int = Query(5, ge=1, le=50), conn=Depends(get_conn), provider=Depends(get_recommender)):
        try:
            svc = provider.get()
            products = [dict(r) for r in conn.execute("SELECT * FROM products")]
            return svc.simulate(products, k=k)
        except RecommenderUnavailable as exc:
            return _empty_report(str(exc), True, k)
        except Exception as exc:
            return _empty_report(str(exc) if is_insufficient(exc) else f"Simulation error: {exc}", True, k)

    return app


app = create_app()
