"""
utils/duck_session.py
──────────────────────
Manages DuckDB in-memory connections.

Each "SQL session" gets its own DuckDB connection with all registered
DataFrames mounted as virtual tables. DuckDB can JOIN, aggregate, and
window-function across them with zero setup — no DB server needed.

Architecture:
  session_id (UUID)
      └─ DuckDB connection
          ├─ table: "sales"       ← pd.DataFrame registered via duckdb.register()
          ├─ table: "employees"
          └─ table: "products"
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import duckdb
import pandas as pd

from models.sql_schemas import TableInfo, SQLSessionInfo


class DuckSession:
    """A single DuckDB connection with metadata about registered tables."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.conn = duckdb.connect(database=":memory:")
        self.tables: Dict[str, TableInfo] = {}      # table_name → TableInfo
        self.created_at = datetime.utcnow().isoformat()
        self._lock = threading.RLock()

    def register(self, table_name: str, df: pd.DataFrame, file_id: str) -> TableInfo:
        """Mount a DataFrame as a virtual SQL table."""
        with self._lock:
            # DuckDB registers by reference — extremely fast, no copy
            self.conn.register(table_name, df)

            info = TableInfo(
                table_name=table_name,
                file_id=file_id,
                row_count=len(df),
                columns=list(df.columns),
                column_types={col: str(df[col].dtype) for col in df.columns},
            )
            self.tables[table_name] = info
            return info

    def execute(self, sql: str) -> pd.DataFrame:
        """Run SQL and return result as DataFrame."""
        with self._lock:
            return self.conn.execute(sql).df()

    def to_session_info(self) -> SQLSessionInfo:
        return SQLSessionInfo(
            session_id=self.session_id,
            tables=list(self.tables.values()),
            created_at=self.created_at,
        )


class DuckSessionStore:
    """Thread-safe registry of all active DuckDB sessions."""

    def __init__(self):
        self._sessions: Dict[str, DuckSession] = {}
        self._lock = threading.RLock()

    def create(self) -> DuckSession:
        session_id = str(uuid.uuid4())
        session = DuckSession(session_id)
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[DuckSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.conn.close()

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions


# Singleton
duck_store = DuckSessionStore()
