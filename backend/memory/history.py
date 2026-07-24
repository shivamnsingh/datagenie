from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List


STORAGE_PATH = Path(".data")
STORAGE_PATH.mkdir(exist_ok=True)
HISTORY_FILE = STORAGE_PATH / "query_history.json"


@dataclass
class QueryHistoryItem:
    session_id: str
    timestamp: str
    question: str
    sql: str
    execution_time_ms: float
    rows_returned: int


class QueryHistoryStore:
    def __init__(self, filepath: Path | None = None):
        self.filepath = filepath or HISTORY_FILE
        self._lock = threading.RLock()
        self._items: List[QueryHistoryItem] = []
        self._load()

    def _load(self):
        if not self.filepath.exists():
            self._items = []
            return
        try:
            with self.filepath.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._items = [QueryHistoryItem(**it) for it in data]
        except Exception:
            self._items = []

    def _persist(self):
        try:
            with self.filepath.open("w", encoding="utf-8") as f:
                json.dump([asdict(i) for i in self._items], f, indent=2)
        except Exception:
            pass

    def add(self, session_id: str, question: str, sql: str, execution_time_ms: float, rows_returned: int):
        item = QueryHistoryItem(
            session_id=session_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            question=question,
            sql=sql,
            execution_time_ms=execution_time_ms,
            rows_returned=rows_returned,
        )
        with self._lock:
            self._items.append(item)
            # keep last 1000
            self._items = self._items[-1000:]
            self._persist()

    def list(self, limit: int = 100, session_id: str | None = None):
        with self._lock:
            items = list(self._items)
            if session_id:
                items = [i for i in items if getattr(i, 'session_id', None) == session_id]
            items = items[-limit:][::-1]
            return items
