# Brickwise — Architecture and interface contracts

```
 Rebrickable CSV (sets, themes) ─► brickwise.data ─► data/brickwise.db (products) + data/images/*.jpg
                                                            │
                          data/images ─► brickwise.ml.embeddings (CLIP ViT-B/32, cached) ─► data/embeddings.npy + data/embedding_ids.json
                                                            │
 React (Vite, :5173) ──/api proxy──► FastAPI (:8000) ──► SQLite feedback ──► brickwise.ml.service (LogReg + FAISS + eval)
```

Repo: `backend/brickwise/{data,ml,api}` (python pkg, run from `backend/`), `frontend/`, `data/` (gitignored artefacts), `docs/`.
Python: use `<repo>/.venv/bin/python` (3.12; torch, open_clip, faiss-cpu, sklearn, fastapi, pytest, httpx installed). Run tests from `backend/`: `../.venv/bin/python -m pytest tests/<area>`.
Path helpers: `brickwise/paths.py` exposes `ROOT, DATA_DIR, IMAGES_DIR, DB_PATH, EMBEDDINGS_PATH, EMBEDDING_IDS_PATH`. Env var `BRICKWISE_DATA_DIR` overrides DATA_DIR (tests use tmp dirs).

## Data contract (ingestion → everything else)
`python -m brickwise.data.ingest --limit 800` (run from `backend/`): downloads Rebrickable `sets.csv.gz` + `themes.csv.gz` (https://cdn.rebrickable.com/media/downloads/), caches raw CSV under `data/raw/`, cleans/validates, selects ~800 diverse sets (multiple themes, num_parts>=10, has img_url, deterministic seed, prefer sets with real photos), downloads images from `img_url` (CDN, no key needed; polite concurrency, retries, skip existing, verify with Pillow, resize to max 512px JPEG) into `data/images/<set_num>.jpg`, writes `products` table (schema.sql) into `data/brickwise.db`. Idempotent. Also `--offline-sample` mode generating a handful of synthetic placeholder images (clearly labelled) for tests/no-network. Prints a validation report (counts, themes, dropped rows + reasons) and writes `data/ingest_report.json`. Document image/data licensing in the module docstring (Rebrickable's terms are unverified; see NOTICE.md).
Public python API: `brickwise.data.products.load_products(db_path=None) -> list[dict]` (keys per schema).

## ML contract (ML package → API)
Artefacts: `data/embeddings.npy` float32 [N,512] L2-normalised, `data/embedding_ids.json` list of set_num aligned to rows. CLI: `python -m brickwise.ml.embeddings` (incremental: only embeds ids missing from cache; CLIP via open_clip `ViT-B-32`/`laion2b_s34b_b79k`, CPU/MPS ok, batch).
Public API in `brickwise/ml/service.py`:
```python
MIN_LIKES = 3; MIN_PASSES = 3          # required before LogReg is trained
class RecommenderService:
    def __init__(self, embeddings_path=None, ids_path=None)   # loads cache; builds FAISS index (fallback: numpy cosine, flag `backend` = "faiss"|"numpy")
    def ids(self) -> list[str]
    def status(self, feedback: dict[str,int]) -> dict   # {ready: bool, likes, passes, min_likes, min_passes, reason: str|None, backend}
    def fit(self, feedback: dict[str,int]) -> dict      # trains LogisticRegression (class_weight balanced, L2); retrains from scratch each call; returns status+{trained_on:int, train_accuracy}; raises InsufficientFeedback (subclass of ValueError) when below mins
    def recommend(self, feedback, k=5, method="logreg") -> list[dict]   # method in {"logreg","similarity"}; excludes ALL rated ids, no duplicates; raises InsufficientFeedback for logreg when not ready, for similarity when 0 likes
       # item: {"set_num", "score": float 0..1, "method", "explanation": str, "similar_to": [{"set_num","similarity"}]}  (similar_to = up to 3 liked sets nearest to the item)
    def similar_to_liked(self, feedback, k=5) -> list[dict]  # FAISS NN baseline: score = mean of top-m cosine to liked set; same item shape
    def evaluate(self, feedback, k=5, n_repeats=20, seed=0) -> dict   # REAL held-out eval on the user's actual ratings (see below)
    def simulate(self, products: list[dict], k=5, seed=0, ...) -> dict # SIMULATED eval: synthetic user whose likes = chosen theme(s); same report shape with "simulated": True
```
Evaluation report shape: `{"simulated": bool, "k": 5, "sufficient": bool, "reason": str|None, "n_ratings", "n_likes", "n_passes", "n_splits", "protocol": str, "methods": {"logreg": {"precision_at_k": float, "std": float}, "similarity": {...}, "random": {...}}, "winner": str|None, "base_rate": float}`. Real eval: repeated stratified hold-out (e.g. 70/30, requires >=10 ratings with >=4 of each class, else `sufficient=false`); P@K = fraction liked among the K highest-scored held-out items (K=min(5, n_test)). Pure helper `precision_at_k(ranked_labels, k)` must be exported and unit-tested. Explanations are plain English ("Looks like Millennium Falcon, which you liked (0.83 similar); the model also predicts 87% you'd like it").

## API contract (API → frontend) — base `/api`, JSON; TypeScript mirror: `frontend/src/api/types.ts`
- `GET /api/health` → `{status:"ok", products:int, embeddings:int, faiss:bool}`
- `GET /api/products/next?limit=1` → `{items: Product[], remaining:int, total:int}` — UNRATED products only, deterministic shuffled order (stable seed) so UI doesn't repeat.
- `POST /api/feedback` body `{set_num, rating:0|1}` → 201 `{feedback, remaining}`; 404 unknown product; 409 duplicate; 422 bad rating.
- `POST /api/feedback/undo` → `{undone: Feedback, remaining}` removes the most recent feedback (by id); 404 when none.
- `GET /api/feedback` → `{items: (Feedback & {product: Product})[], likes, passes}`
- `DELETE /api/feedback` → 204 reset profile.
- `GET /api/preferences` → PreferenceSummary (likes, passes, total_rated, remaining, top_themes[{theme,likes,passes,like_rate}], avg_parts_liked, avg_parts_passed, model: status dict)
- `GET /api/recommendations?k=5&method=logreg|similarity` → `{status:"ok"|"insufficient_feedback", method, message, min_likes, min_passes, likes, passes, items: Recommendation[]}` (200 in both cases; items empty when insufficient). Recommendation = `{product, score, explanation, similar_to:[{product, similarity}]}`.
- `GET /api/evaluation` → real EvaluationReport. `POST /api/evaluation/simulate` → simulated report. Frontend must label simulated clearly.
- Images: backend mounts `data/images` at `/images/<file>`; Product.image_url = `/images/<image_file>`. Vite dev proxy forwards `/api` and `/images` to :8000.
- Errors: FastAPI default `{detail: ...}`.
The backend must work (health, products, feedback, undo, preferences) even when embeddings.npy is missing; recommendations/evaluation then return `status:"unavailable"` message. Backend integrates ML ONLY through RecommenderService (lazy-loaded singleton, reloadable).
Run: `cd backend && ../.venv/bin/uvicorn brickwise.api.main:app --port 8000`.

## Frontend
React+TS+Vite+Tailwind (+shadcn-style components where useful), vitest + Testing Library, in `frontend/`. Routes: `/` Discover, `/recommendations`, `/profile` (preference summary), `/evaluation`. Brand: "Brickwise — Discover builds that match you." Original identity (own colours/logo mark; do not copy LEGO® logo/trade dress; include non-affiliation footer + Rebrickable attribution). Card w/ image, name, set id, theme, pieces, year; Like / Pass buttons + keyboard (←/→/Z) + optional drag-swipe; Undo; remaining counter; loading/empty/error/insufficient-feedback states; responsive. Typed API client in `src/api/`. Must pass `npm run typecheck`, `npm test`, `npm run build`. Mock API via MSW-free fetch mocking in tests (no backend needed).
