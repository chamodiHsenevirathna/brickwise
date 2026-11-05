"""Honest offline evaluation: precision@K, repeated stratified hold-out, simulation."""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

MIN_RATINGS = 10
MIN_PER_CLASS = 4
TEST_SIZE = 0.3
TOP_M = 3


def precision_at_k(ranked_labels, k: int) -> float:
    """Fraction of positives among the first k labels of a ranked list (0.0 for k<=0 or empty)."""
    labels = list(ranked_labels)[: max(int(k), 0)]
    if not labels:
        return 0.0
    return float(sum(1 for x in labels if x) / len(labels))


def fit_logreg(X: np.ndarray, y: np.ndarray) -> LogisticRegression:
    clf = LogisticRegression(class_weight="balanced", C=1.0, max_iter=1000)
    clf.fit(X, y)
    return clf


def similarity_scores(X_liked: np.ndarray, X_cand: np.ndarray, m: int = TOP_M) -> np.ndarray:
    """Mean of the top-m cosine similarities (inputs L2-normalised) to the liked set."""
    sims = X_cand @ X_liked.T
    m = min(m, sims.shape[1])
    top = -np.sort(-sims, axis=1)[:, :m]
    return top.mean(axis=1)


def _empty_report(simulated, k, reason, y, protocol):
    n = int(len(y))
    likes = int(np.sum(y)) if n else 0
    return {"simulated": simulated, "k": k, "sufficient": False, "reason": reason,
            "n_ratings": n, "n_likes": likes, "n_passes": n - likes, "n_splits": 0,
            "protocol": protocol, "methods": {}, "winner": None,
            "base_rate": (likes / n) if n else 0.0}


def sufficiency(y: np.ndarray) -> str | None:
    n = len(y)
    likes = int(np.sum(y))
    passes = n - likes
    if n < MIN_RATINGS:
        return f"Need at least {MIN_RATINGS} ratings to evaluate honestly (you have {n})."
    if likes < MIN_PER_CLASS or passes < MIN_PER_CLASS:
        return (f"Need at least {MIN_PER_CLASS} likes and {MIN_PER_CLASS} passes "
                f"(you have {likes} likes, {passes} passes).")
    return None


def holdout_scores(X, y, k=5, n_repeats=20, seed=0) -> dict[str, list[float]]:
    """Per-split P@K for logreg / similarity / random."""
    rng = np.random.default_rng(seed)
    out = {"logreg": [], "similarity": [], "random": []}
    for r in range(n_repeats):
        try:
            tr, te = train_test_split(np.arange(len(y)), test_size=TEST_SIZE,
                                      stratify=y, random_state=int(rng.integers(1 << 31)))
        except ValueError:
            continue
        if len(set(y[tr])) < 2:
            continue
        kk = min(k, len(te))
        Xtr, Xte, ytr, yte = X[tr], X[te], y[tr], y[te]
        s_lr = fit_logreg(Xtr, ytr).predict_proba(Xte)[:, 1]
        s_sim = similarity_scores(Xtr[ytr == 1], Xte)
        s_rnd = rng.random(len(te))
        for name, s in (("logreg", s_lr), ("similarity", s_sim), ("random", s_rnd)):
            order = np.argsort(-s, kind="stable")
            out[name].append(precision_at_k(yte[order], kk))
    return out


def summarise(scores: dict[str, list[float]], y_all, k, simulated, protocol, extra=None) -> dict:
    n = int(len(y_all))
    likes = int(np.sum(y_all))
    n_splits = len(scores["logreg"])
    if n_splits == 0:
        return _empty_report(simulated, k, "No valid train/test split could be formed.", y_all, protocol)
    methods = {m: {"precision_at_k": float(np.mean(v)), "std": float(np.std(v))} for m, v in scores.items()}
    best = max(methods, key=lambda m: methods[m]["precision_at_k"])
    tied = [m for m in methods if abs(methods[m]["precision_at_k"] - methods[best]["precision_at_k"]) < 1e-9]
    rep = {"simulated": simulated, "k": k, "sufficient": True, "reason": None,
           "n_ratings": n, "n_likes": likes, "n_passes": n - likes, "n_splits": n_splits,
           "protocol": protocol, "methods": methods,
           "winner": best if len(tied) == 1 else None, "base_rate": likes / n}
    if extra:
        rep.update(extra)
    return rep


def evaluate_ratings(X, y, k=5, n_repeats=20, seed=0, simulated=False, extra=None) -> dict:
    y = np.asarray(y, dtype=int)
    protocol = (f"Repeated stratified hold-out: {n_repeats} random {int((1-TEST_SIZE)*100)}/"
                f"{int(TEST_SIZE*100)} splits; models trained on the train part, ranking the held-out "
                f"items; P@K = share of liked items among the top K (K=min({k}, test size)).")
    reason = sufficiency(y)
    if reason:
        return _empty_report(simulated, k, reason, y, protocol)
    scores = holdout_scores(np.asarray(X, dtype=np.float32), y, k, n_repeats, seed)
    return summarise(scores, y, k, simulated, protocol, extra)


def simulate_user(products, ids_index: dict[str, int], rng, n_themes=None, n_rated=120, noise=0.1,
                  min_like_frac=0.15):
    """Synthetic user. Returns (row_indices, labels, chosen_themes) or None."""
    by_theme: dict[str, list[int]] = {}
    for p in products:
        i = ids_index.get(p["set_num"])
        if i is not None:
            by_theme.setdefault(p["root_theme"], []).append(i)
    themes = sorted(t for t, v in by_theme.items() if len(v) >= 5)
    if len(themes) < 2:
        return None
    all_idx = sorted(i for v in by_theme.values() for i in v)
    n_themes = n_themes or int(rng.integers(1, 4))
    n_themes = min(n_themes, len(themes) - 1)
    order = [themes[j] for j in rng.permutation(len(themes))]
    chosen = order[:n_themes]
    liked_set = {i for t in chosen for i in by_theme[t]}
    # If the catalogue is split into many tiny root themes, 1-3 themes would give almost no likes.
    # Keep adding randomly chosen themes until at least min_like_frac of products are liked.
    for t in order[n_themes:]:
        if len(liked_set) >= min_like_frac * len(all_idx) or len(chosen) >= len(themes) - 1:
            break
        chosen.append(t)
        liked_set |= set(by_theme[t])
    rated = rng.choice(all_idx, size=min(n_rated, len(all_idx)), replace=False)
    labels = np.array([1 if i in liked_set else 0 for i in rated], dtype=int)
    flip = rng.random(len(labels)) < noise
    labels = np.where(flip, 1 - labels, labels)
    return np.array(rated), labels, chosen


def simulate(emb: np.ndarray, ids: list[str], products, k=5, seed=0, n_users=5, n_rated=120,
             noise=0.1, n_repeats=20, min_like_frac=0.15) -> dict:
    protocol = ("SIMULATED: synthetic users like every product in 1-3 randomly chosen root themes "
                f"(more themes are added if needed so >= {int(min_like_frac*100)}% of products are liked), "
                f"with {int(noise*100)}% label noise, and rate a random subset of {n_rated} products; "
                f"{n_users} users x {n_repeats} stratified hold-out splits. Not real user data.")
    rng = np.random.default_rng(seed)
    idx = {s: i for i, s in enumerate(ids)}
    pooled = {"logreg": [], "similarity": [], "random": []}
    ys, themes_used = [], []
    for u in range(n_users):
        sim = simulate_user(products, idx, rng, n_rated=n_rated, noise=noise, min_like_frac=min_like_frac)
        if sim is None:
            break
        rows, y, chosen = sim
        if sufficiency(y):
            continue
        sc = holdout_scores(emb[rows], y, k, n_repeats, int(rng.integers(1 << 31)))
        for m in pooled:
            pooled[m].extend(sc[m])
        ys.append(y)
        themes_used.append(chosen)
    if not ys:
        return _empty_report(True, k, "Not enough labelled products/embeddings to simulate a user.",
                             np.array([], dtype=int), protocol)
    return summarise(pooled, np.concatenate(ys), k, True, protocol,
                     {"n_users": len(ys), "simulated_themes": themes_used})
