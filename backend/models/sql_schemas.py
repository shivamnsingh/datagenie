"""
models/sql_schemas.py
──────────────────────
Pydantic models for the Text-to-SQL engine.
"""

from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════
# SESSION / REGISTRATION
# ══════════════════════════════════════════════════════════════════

class RegisterTableRequest(BaseModel):
    """Register one cleaned dataset as a SQL table."""
    file_id: str
    table_name: str         # e.g. "sales", "employees"


class RegisterTablesRequest(BaseModel):
    """Register multiple datasets at once (for multi-table sessions)."""
    tables: List[RegisterTableRequest]


class TableInfo(BaseModel):
    table_name: str
    file_id: str
    row_count: int
    columns: List[str]
    column_types: Dict[str, str]    # col_name → dtype string


class SQLSessionInfo(BaseModel):
    session_id: str
    tables: List[TableInfo]
    created_at: str


# ══════════════════════════════════════════════════════════════════
# QUERY
# ══════════════════════════════════════════════════════════════════

class NLQueryRequest(BaseModel):
    session_id: str
    question: str                   # natural language question
    max_rows: int = 500             # cap result size


class SQLQueryRequest(BaseModel):
    """Run a raw SQL query directly (for power users / debug)."""
    session_id: str
    sql: str
    max_rows: int = 500


class QueryColumn(BaseModel):
    name: str
    dtype: str


class VizSuggestion(BaseModel):
    chart_type: Literal["bar", "line", "pie", "histogram", "heatmap", "scatter", "table"]
    x_col: Optional[str] = None
    y_col: Optional[str] = None
    color_col: Optional[str] = None
    title: str
    reason: str                     # why this chart was suggested


class QueryResult(BaseModel):
    session_id: str
    question: str                   # original NL question
    sql: str                        # generated or raw SQL
    sql_explanation: str            # plain-English explanation of the SQL
    columns: List[QueryColumn]
    rows: List[Dict[str, Any]]
    row_count: int
    truncated: bool                 # True if result was capped at max_rows
    execution_time_ms: float
    viz_suggestion: Optional[VizSuggestion] = None
    error: Optional[str] = None     # non-null if query failed


# ══════════════════════════════════════════════════════════════════
# HISTORY
# ══════════════════════════════════════════════════════════════════

class QueryHistoryItem(BaseModel):
    question: str
    sql: str
    row_count: int
    timestamp: str


class QueryHistoryResponse(BaseModel):
    session_id: str
    history: List[QueryHistoryItem]
