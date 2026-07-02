"""
utils/session_store.py
───────────────────────
Thread-safe in-memory store mapping file_id → pd.DataFrame.

Bounded with a TTL + max-size cache so DataFrames don't accumulate
forever across the life of the process (previously an unbounded dict —
the main driver of gradual memory growth / OOM kills on Render Free).

In production, swap this for Redis + Parquet on S3.
"""

import threading
from typing import Dict, Optional
import pandas as pd
from cachetools import TTLCache

# Max concurrently-cached DataFrames and how long each lives before
# automatic eviction. Tuned for Render Free (512 MB): a handful of
# downcast DataFrames (originals + cleaned copies) comfortably fit
# this budget without risking unbounded growth.
_MAXSIZE = 10
_TTL_SECONDS = 1800  # 30 minutes


class SessionStore:
    """Simple dict-backed store with read/write locks. Entries expire automatically."""

    def __init__(self, maxsize: int = _MAXSIZE, ttl: int = _TTL_SECONDS) -> None:
        self._store: "TTLCache[str, pd.DataFrame]" = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.RLock()

    def save(self, file_id: str, df: pd.DataFrame) -> None:
        with self._lock:
            self._store.expire()
            self._store[file_id] = df

    def load(self, file_id: str, copy: bool = True) -> Optional[pd.DataFrame]:
        with self._lock:
            self._store.expire()
            df = self._store.get(file_id)
            if df is None:
                return None
            return df.copy() if copy else df

    def delete(self, file_id: str) -> None:
        with self._lock:
            self._store.pop(file_id, None)

    def exists(self, file_id: str) -> bool:
        with self._lock:
            self._store.expire()
            return file_id in self._store

    def list_ids(self):
        with self._lock:
            self._store.expire()
            return list(self._store.keys())


# Singleton used across the app
store = SessionStore()
