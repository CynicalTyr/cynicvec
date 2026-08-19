"""cynicvec.py — thin wrapper over turbovec IdMapIndex (4-bit).

Additive accelerator for KNN recall. The SQL/vector table stays
authoritative; this owns only the ``.tvim`` lifecycle. External ids ARE
source rowids (uint64) so there is no side-car map. Fail-open: a raised
``RuntimeError`` (turbovec missing) means the caller must use the SQL path.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    from turbovec import IdMapIndex
    _HAS_TURBOVEC = True
except ImportError:  # pragma: no cover - environment-dependent
    IdMapIndex = None  # type: ignore[assignment]
    _HAS_TURBOVEC = False


class CynicVec:
    """Thread-safe wrapper over a single ``turbovec.IdMapIndex`` (.tvim file)."""

    def __init__(
        self,
        index_path: Path | str,
        dim: int = 2048,
        bit_width: int = 4,
        *,
        reload_on_mtime: bool = True,
    ) -> None:
        if not _HAS_TURBOVEC:
            raise RuntimeError(
                "turbovec not installed; caller must fall back to the SQL vector path"
            )
        self.index_path = Path(index_path)
        self.dim = int(dim)
        self.bit_width = int(bit_width)
        # Benchmarks pin the snapshot so concurrent dual-writes cannot
        # force a mid-run IdMapIndex.load (multi-second) into latency samples.
        self.reload_on_mtime = bool(reload_on_mtime)
        self._index: "IdMapIndex | None" = None
        self._prepared = False
        self._dirty = False
        self._loaded_mtime_ns: int | None = None
        self._lock = threading.Lock()

    def _as_query(self, vector) -> np.ndarray:
        v = np.asarray(vector, dtype=np.float32).ravel()
        if v.shape[0] != self.dim:
            raise ValueError(f"vector dim mismatch: got {v.shape[0]}, expected {self.dim}")
        return v.reshape(1, self.dim)

    def _ensure_loaded(self) -> bool:
        if self._index is None:
            if self.index_path.exists():
                self._index = IdMapIndex.load(str(self.index_path))
                self._loaded_mtime_ns = os.stat(self.index_path).st_mtime_ns
                return True
            self._index = IdMapIndex(self.dim, self.bit_width)
            self._loaded_mtime_ns = None
            return False
        exists = self.index_path.exists()
        if self.reload_on_mtime and not self._dirty and exists:
            mtime_ns = os.stat(self.index_path).st_mtime_ns
            if mtime_ns != self._loaded_mtime_ns:
                self._index = IdMapIndex.load(str(self.index_path))
                self._prepared = False
                self._loaded_mtime_ns = mtime_ns
        return exists

    def _prepare_if_needed(self) -> None:
        if self._index is not None and not self._prepared:
            self._index.prepare()
            self._prepared = True

    def add(self, rowid: int, vector: Iterable[float]) -> None:
        with self._lock:
            self._ensure_loaded()
            v = self._as_query(vector)
            ids = np.asarray([rowid], dtype=np.uint64)
            self._index.add_with_ids(v, ids)
            self._prepared = False
            self._dirty = True

    def add_batch(self, rowids: Iterable[int], vectors) -> None:
        with self._lock:
            self._ensure_loaded()
            v = np.asarray(vectors, dtype=np.float32).reshape(-1, self.dim)
            ids = np.asarray(list(rowids), dtype=np.uint64)
            if v.shape[0] != ids.shape[0]:
                raise ValueError(f"rowids/vectors length mismatch: {ids.shape[0]} vs {v.shape[0]}")
            self._index.add_with_ids(v, ids)
            self._prepared = False
            self._dirty = True

    def remove(self, rowid: int) -> bool:
        with self._lock:
            self._ensure_loaded()
            if self._index is None:
                return False
            ok = bool(self._index.remove(np.uint64(rowid)))
            if ok:
                self._prepared = False
                self._dirty = True
            return ok

    def present_ids(self, rowids: Iterable[int]) -> list[int]:
        """Return the subset of ``rowids`` currently in the index.

        turbovec's ``search(allowlist=)`` raises if the allowlist names an id the
        index does not hold (e.g. a metadata row whose vector was skipped or added
        after the last backfill). Callers intersect first to stay fail-safe.
        """
        with self._lock:
            if self._index is None and not self.index_path.exists():
                return []
            self._ensure_loaded()
            if self._index is None:
                return []
            idx = self._index
            return [int(r) for r in rowids if idx.contains(np.uint64(int(r)))]

    def search(self, query_vec: Iterable[float], k: int = 10,
               allowlist: Iterable[int] | None = None) -> list[tuple[int, float]]:
        with self._lock:
            if self._index is None and not self.index_path.exists():
                return []
            self._ensure_loaded()
            al = None
            if allowlist is not None:
                al = np.asarray(list(allowlist), dtype=np.uint64)
                if al.size == 0:
                    return []
            self._prepare_if_needed()
            q = self._as_query(query_vec)
            scores, ids = self._index.search(q, int(k), allowlist=al)
            return [(int(i), float(s)) for i, s in zip(ids[0].tolist(), scores[0].tolist())]

    def save(self) -> None:
        with self._lock:
            if self._index is None or not self._dirty:
                return
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
            prev_size = self.index_path.stat().st_size if self.index_path.exists() else 0
            self._index.write(str(tmp))
            new_size = tmp.stat().st_size
            # Refuse to atomically replace a large backfilled index with a tiny
            # in-memory snapshot (dual-write must not clobber .tvim).
            if prev_size > 50_000_000 and new_size < prev_size * 0.5:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(
                    f"cynicvec save blocked: would shrink index "
                    f"{prev_size} -> {new_size} bytes"
                )
            os.replace(tmp, self.index_path)
            self._dirty = False
            self._loaded_mtime_ns = os.stat(self.index_path).st_mtime_ns
