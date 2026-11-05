"""Adapter around ``brickwise.ml.service.RecommenderService``.

The API talks to the ML layer only through this module: a lazy, reloadable
singleton that never raises at import time. If the ML package or the embeddings
cache is missing, ``get()`` raises ``RecommenderUnavailable`` and the routes
degrade to ``status: "unavailable"``.
"""
from __future__ import annotations

import threading
from pathlib import Path

try:  # use the real exception when the ML package is importable
    from brickwise.ml.service import InsufficientFeedback  # type: ignore
except Exception:  # pragma: no cover - fallback if the ML package cannot be imported
    class InsufficientFeedback(ValueError):  # type: ignore[no-redef]
        """Fallback; mirrors brickwise.ml.service.InsufficientFeedback."""


def is_insufficient(exc: BaseException) -> bool:
    """True for the real or fallback InsufficientFeedback (matched by name too)."""
    return isinstance(exc, InsufficientFeedback) or type(exc).__name__ == "InsufficientFeedback"


class RecommenderUnavailable(RuntimeError):
    pass


class LazyRecommender:
    """Lazy singleton; rebuilt when the embeddings files change or on reload()."""

    def __init__(self, embeddings_path: Path, ids_path: Path):
        self.embeddings_path = Path(embeddings_path)
        self.ids_path = Path(ids_path)
        self._service = None
        self._stamp = None
        self._lock = threading.Lock()

    def _current_stamp(self):
        try:
            return (self.embeddings_path.stat().st_mtime_ns, self.ids_path.stat().st_mtime_ns)
        except OSError:
            return None

    def reload(self) -> None:
        with self._lock:
            self._service = None
            self._stamp = None

    def get(self):
        stamp = self._current_stamp()
        if stamp is None:
            raise RecommenderUnavailable(
                "Embeddings not found. Run `python -m brickwise.ml.embeddings` to build them."
            )
        with self._lock:
            if self._service is not None and stamp == self._stamp:
                return self._service
            try:
                from brickwise.ml.service import RecommenderService  # lazy
                self._service = RecommenderService(self.embeddings_path, self.ids_path)
            except Exception as exc:  # import error, corrupt cache, ...
                self._service = None
                raise RecommenderUnavailable(f"Recommender could not be loaded: {exc}") from exc
            self._stamp = stamp
            return self._service


class StaticProvider:
    """Provider wrapping an already-built service (used by tests)."""

    def __init__(self, service):
        self.service = service

    def get(self):
        return self.service

    def reload(self) -> None:
        pass
