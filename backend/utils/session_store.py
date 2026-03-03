"""
utils/session_store.py
───────────────────────
Thread-safe in-memory store mapping file_id → pd.DataFrame.

In production, swap this for Redis + Parquet on S3.
"""

import threading
from typing import Dict, Optional
import pandas as pd


class SessionStore:
    """Simple dict-backed store with read/write locks."""

    def __init__(self) -> None:
        self._store: Dict[str, pd.DataFrame] = {}
        self._lock = threading.RLock()

    def save(self, file_id: str, df: pd.DataFrame) -> None:
        with self._lock:
            self._store[file_id] = df.copy()

    def load(self, file_id: str) -> Optional[pd.DataFrame]:
        with self._lock:
            df = self._store.get(file_id)
            return df.copy() if df is not None else None

    def delete(self, file_id: str) -> None:
        with self._lock:
            self._store.pop(file_id, None)

    def exists(self, file_id: str) -> bool:
        with self._lock:
            return file_id in self._store

    def list_ids(self):
        with self._lock:
            return list(self._store.keys())


# Singleton used across the app
store = SessionStore()
