"""CLIP image embeddings for Brickwise products.

Model: open_clip ViT-B-32 / laion2b_s34b_b79k (weights from HuggingFace, free).
Output: data/embeddings.npy (float32 [N,512], L2-normalised) and
data/embedding_ids.json (set_num per row). Incremental: only ids missing from
the cache are embedded. torch/open_clip are imported lazily.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from .. import paths

MODEL_NAME = "ViT-B-32"
PRETRAINED = "laion2b_s34b_b79k"


def l2_normalise(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return (x / np.maximum(n, 1e-12)).astype(np.float32)


def _atomic_write(path: Path, writer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    os.close(fd)
    try:
        writer(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_cache(emb: np.ndarray, ids: list[str], emb_path: Path, ids_path: Path) -> None:
    def w_npy(tmp):
        with open(tmp, "wb") as f:
            np.save(f, emb.astype(np.float32))

    def w_ids(tmp):
        with open(tmp, "w") as f:
            json.dump(ids, f)

    _atomic_write(emb_path, w_npy)
    _atomic_write(ids_path, w_ids)


def load_cache(emb_path: Path, ids_path: Path) -> tuple[np.ndarray, list[str]]:
    if not (emb_path.exists() and ids_path.exists()):
        return np.zeros((0, 512), dtype=np.float32), []
    emb = np.load(emb_path)
    ids = json.loads(Path(ids_path).read_text())
    if emb.shape[0] != len(ids):
        return np.zeros((0, 512), dtype=np.float32), []
    return emb.astype(np.float32), ids


def product_images(db_path: Path, images_dir: Path) -> list[tuple[str, Path]]:
    """(set_num, image path) for products whose image file exists."""
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute("SELECT set_num, image_file FROM products ORDER BY set_num").fetchall()
    finally:
        con.close()
    return [(s, images_dir / f) for s, f in rows if (images_dir / f).exists()]


def pick_device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class ClipEncoder:
    def __init__(self, device: str | None = None):
        import open_clip
        import torch

        self.torch = torch
        self.device = device or pick_device()
        model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
        self.model = model.to(self.device).eval()
        self.preprocess = preprocess

    def encode_paths(self, paths_: list[Path]) -> np.ndarray:
        from PIL import Image

        imgs = []
        for p in paths_:
            with Image.open(p) as im:
                imgs.append(self.preprocess(im.convert("RGB")))
        batch = self.torch.stack(imgs).to(self.device)
        with self.torch.no_grad():
            feats = self.model.encode_image(batch)
        return l2_normalise(feats.float().cpu().numpy())


def build_embeddings(db_path=None, images_dir=None, emb_path=None, ids_path=None,
                     batch_size: int = 32, encoder=None, verbose: bool = True) -> dict:
    """Embed products missing from the cache. `encoder` (obj with encode_paths) is injectable for tests."""
    db_path = Path(db_path or paths.DB_PATH)
    images_dir = Path(images_dir or paths.IMAGES_DIR)
    emb_path = Path(emb_path or paths.EMBEDDINGS_PATH)
    ids_path = Path(ids_path or paths.EMBEDDING_IDS_PATH)
    items = product_images(db_path, images_dir)
    emb, ids = load_cache(emb_path, ids_path)
    current = {s for s, _ in items}
    pruned = 0
    if len(ids) and any(s not in current for s in ids):  # drop rows for products no longer in the catalogue
        keep = [i for i, s in enumerate(ids) if s in current]
        pruned = len(ids) - len(keep)
        emb, ids = emb[keep], [ids[i] for i in keep]
        save_cache(emb, ids, emb_path, ids_path)
    have = set(ids)
    todo = [(s, p) for s, p in items if s not in have]
    t0 = time.time()
    if todo:
        encoder = encoder or ClipEncoder()
        chunks = []
        new_ids: list[str] = []
        for i in range(0, len(todo), batch_size):
            part = todo[i:i + batch_size]
            try:
                chunks.append(encoder.encode_paths([p for _, p in part]))
                new_ids.extend(s for s, _ in part)
            except Exception:  # bad image in batch: fall back to one by one
                for s, p in part:
                    try:
                        chunks.append(encoder.encode_paths([p]))
                        new_ids.append(s)
                    except Exception as e:
                        print(f"skip {s}: {e}", file=sys.stderr)
            if verbose:
                print(f"embedded {min(i + batch_size, len(todo))}/{len(todo)}", flush=True)
        if chunks:
            emb = np.vstack([emb] + chunks) if len(ids) else np.vstack(chunks)
            ids = ids + new_ids
            save_cache(emb, ids, emb_path, ids_path)
    return {"total": len(ids), "new": len(todo), "pruned": pruned, "products_with_images": len(items),
            "seconds": round(time.time() - t0, 2)}


def main() -> None:
    print(build_embeddings())


if __name__ == "__main__":
    main()
