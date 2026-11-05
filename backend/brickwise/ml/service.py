"""RecommenderService: logistic regression + FAISS nearest-neighbour over CLIP embeddings."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import paths
from . import evaluation as ev
from .embeddings import load_cache

MIN_LIKES = 3
MIN_PASSES = 3
TOP_M = ev.TOP_M

try:  # pragma: no cover - import guard
    import faiss
except Exception:  # pragma: no cover
    faiss = None


class InsufficientFeedback(ValueError):
    pass


class RecommenderService:
    def __init__(self, embeddings_path=None, ids_path=None, use_faiss: bool = True):
        emb, ids = load_cache(Path(embeddings_path or paths.EMBEDDINGS_PATH),
                              Path(ids_path or paths.EMBEDDING_IDS_PATH))
        self._init(emb, ids, use_faiss)

    @classmethod
    def from_arrays(cls, emb: np.ndarray, ids: list[str], use_faiss: bool = True):
        self = cls.__new__(cls)
        self._init(np.asarray(emb, dtype=np.float32), list(ids), use_faiss)
        return self

    def _init(self, emb, ids, use_faiss):
        self.emb = np.ascontiguousarray(emb, dtype=np.float32)
        self._ids = list(ids)
        self.index_of = {s: i for i, s in enumerate(self._ids)}
        self.backend = "numpy"
        self.index = None
        if use_faiss and faiss is not None and len(self._ids):
            self.index = faiss.IndexFlatIP(self.emb.shape[1])
            self.index.add(self.emb)
            self.backend = "faiss"
        self.model = None

    def ids(self) -> list[str]:
        return list(self._ids)

    # ---------- feedback helpers ----------
    def _clean(self, feedback: dict) -> dict[str, int]:
        return {s: int(r) for s, r in feedback.items() if s in self.index_of and int(r) in (0, 1)}

    def _counts(self, fb):
        likes = sum(1 for r in fb.values() if r == 1)
        return likes, len(fb) - likes

    def status(self, feedback: dict) -> dict:
        fb = self._clean(feedback)
        likes, passes = self._counts(fb)
        reason = None
        if likes < MIN_LIKES or passes < MIN_PASSES:
            need = []
            if likes < MIN_LIKES:
                need.append(f"{MIN_LIKES - likes} more like{'s' if MIN_LIKES - likes != 1 else ''}")
            if passes < MIN_PASSES:
                need.append(f"{MIN_PASSES - passes} more pass{'es' if MIN_PASSES - passes != 1 else ''}")
            reason = "Rate " + " and ".join(need) + " so the model has enough to learn from."
        return {"ready": reason is None, "likes": likes, "passes": passes,
                "min_likes": MIN_LIKES, "min_passes": MIN_PASSES, "reason": reason,
                "backend": self.backend}

    # ---------- similarity ----------
    def _sims_to(self, rows: np.ndarray) -> np.ndarray:
        """Cosine similarity of every embedding to each liked row -> [N, n_liked]."""
        q = self.emb[rows]
        if self.index is not None:
            n = len(self._ids)
            D, I = self.index.search(q, n)  # exact (flat) search over all items
            out = np.empty((n, len(rows)), dtype=np.float32)
            for j in range(len(rows)):
                out[I[j], j] = D[j]
            return out
        return self.emb @ q.T

    def _similar_to(self, sims_row: np.ndarray, liked_ids: list[str]) -> list[dict]:
        order = np.argsort(-sims_row, kind="stable")[:3]
        return [{"set_num": liked_ids[j], "similarity": round(float(sims_row[j]), 4)} for j in order]

    # ---------- training ----------
    def fit(self, feedback: dict) -> dict:
        fb = self._clean(feedback)
        st = self.status(fb)
        if not st["ready"]:
            raise InsufficientFeedback(st["reason"])
        rows = np.array([self.index_of[s] for s in fb])
        y = np.array([fb[s] for s in fb])
        self.model = ev.fit_logreg(self.emb[rows], y)
        st.update(trained_on=int(len(y)), train_accuracy=float(self.model.score(self.emb[rows], y)))
        return st

    # ---------- recommendation ----------
    def _candidates(self, fb):
        return np.array([i for s, i in self.index_of.items() if s not in fb], dtype=int)

    def recommend(self, feedback: dict, k: int = 5, method: str = "logreg") -> list[dict]:
        if method == "similarity":
            return self.similar_to_liked(feedback, k)
        if method != "logreg":
            raise ValueError(f"unknown method {method!r}")
        fb = self._clean(feedback)
        self.fit(fb)  # retrain from scratch; raises InsufficientFeedback
        cand = self._candidates(fb)
        if len(cand) == 0:
            return []
        proba = self.model.predict_proba(self.emb[cand])[:, 1]
        liked = [s for s, r in fb.items() if r == 1]
        sims = self._sims_to(np.array([self.index_of[s] for s in liked]))[cand]
        out = []
        for j in np.argsort(-proba, kind="stable")[:k]:
            sid = self._ids[cand[j]]
            near = self._similar_to(sims[j], liked)
            p = float(proba[j])
            out.append({"set_num": sid, "score": p, "method": "logreg",
                        "explanation": self._explain_logreg(p, near), "similar_to": near})
        return out

    def similar_to_liked(self, feedback: dict, k: int = 5) -> list[dict]:
        fb = self._clean(feedback)
        liked = [s for s, r in fb.items() if r == 1]
        if not liked:
            raise InsufficientFeedback("Like at least one set to get similarity-based suggestions.")
        cand = self._candidates(fb)
        if len(cand) == 0:
            return []
        sims = self._sims_to(np.array([self.index_of[s] for s in liked]))[cand]
        m = min(TOP_M, sims.shape[1])
        score = -np.sort(-sims, axis=1)[:, :m]
        score = np.clip(score.mean(axis=1), 0.0, 1.0)
        out = []
        for j in np.argsort(-score, kind="stable")[:k]:
            near = self._similar_to(sims[j], liked)
            out.append({"set_num": self._ids[cand[j]], "score": float(score[j]), "method": "similarity",
                        "explanation": self._explain_sim(float(score[j]), near, m), "similar_to": near})
        return out

    @staticmethod
    def _explain_logreg(p, near) -> str:
        parts = []
        if near:
            names = ", ".join(f"{n['set_num']} ({n['similarity']:.2f} similar)" for n in near[:2])
            parts.append(f"Looks like {names}, which you liked")
        parts.append(f"the model predicts {round(p * 100)}% you'd like it")
        txt = "; ".join(parts)
        return txt[0].upper() + txt[1:] + "."

    @staticmethod
    def _explain_sim(score, near, m) -> str:
        names = ", ".join(f"{n['set_num']} ({n['similarity']:.2f} similar)" for n in near[:2])
        return (f"Visually closest to {names}, which you liked; "
                f"average similarity to your liked sets' nearest matches is {score:.2f}.")

    # ---------- evaluation ----------
    def evaluate(self, feedback: dict, k: int = 5, n_repeats: int = 20, seed: int = 0) -> dict:
        fb = self._clean(feedback)
        rows = np.array([self.index_of[s] for s in fb], dtype=int)
        y = np.array([fb[s] for s in fb], dtype=int)
        X = self.emb[rows] if len(rows) else np.zeros((0, self.emb.shape[1]), dtype=np.float32)
        return ev.evaluate_ratings(X, y, k=k, n_repeats=n_repeats, seed=seed, simulated=False)

    def simulate(self, products: list[dict], k: int = 5, seed: int = 0, n_users: int = 5,
                 n_rated: int = 120, noise: float = 0.1, n_repeats: int = 20,
                 min_like_frac: float = 0.15) -> dict:
        return ev.simulate(self.emb, self._ids, products, k=k, seed=seed, n_users=n_users,
                           n_rated=n_rated, noise=noise, n_repeats=n_repeats, min_like_frac=min_like_frac)
