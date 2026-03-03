"""
routers/sql.py
───────────────
POST /api/sql/session          — create a new SQL session, register tables
GET  /api/sql/session/{id}     — inspect a session (tables, columns)
POST /api/sql/query            — natural language → SQL → execute
POST /api/sql/raw              — execute raw SQL directly
GET  /api/sql/history/{id}     — query history for a session
DELETE /api/sql/session/{id}   — close and free a session
"""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Header
from typing import Annotated, Optional

from models.sql_schemas import (
    NLQueryRequest,
    QueryHistoryItem,
    QueryHistoryResponse,
    QueryResult,
    RegisterTablesRequest,
    SQLQueryRequest,
    SQLSessionInfo,
)
from services.sql_service import execute_raw_sql, nl_to_sql_and_execute
from utils.duck_session import duck_store
from utils.session_store import store as df_store

router = APIRouter()

# Simple in-memory history store per session
# session_id → list of QueryHistoryItem
_history: dict[str, list] = {}


# ── Create session + register tables ─────────────────────────────────────────

@router.post("/session", response_model=SQLSessionInfo)
def create_session(req: RegisterTablesRequest):
    """
    Create a new DuckDB SQL session and register DataFrames as tables.

    Example request:
    {
      "tables": [
        {"file_id": "uuid-1", "table_name": "sales"},
        {"file_id": "uuid-2", "table_name": "employees"}
      ]
    }
    """
    session = duck_store.create()

    for t in req.tables:
        df = df_store.load(t.file_id)
        if df is None:
            duck_store.delete(session.session_id)
            raise HTTPException(
                status_code=404,
                detail=f"File ID '{t.file_id}' not found. "
                       "Upload and clean the file first before creating a SQL session.",
            )
        session.register(t.table_name, df, t.file_id)

    _history[session.session_id] = []
    return session.to_session_info()


# ── Inspect session ────────────────────────────────────────────────────────────

@router.get("/session/{session_id}", response_model=SQLSessionInfo)
def get_session(session_id: str):
    session = duck_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session.to_session_info()


# ── Natural language query ─────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResult)
async def nl_query(
    req: NLQueryRequest,
    x_api_key: Annotated[Optional[str], Header()] = None,
):
    """
    Translate a natural language question to SQL, execute it, and return results.

    Pass your Anthropic API key as the 'x-api-key' header.
    In production, load it from environment variables instead.
    """
    session = duck_store.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{req.session_id}' not found.")

    # Resolve API key: header > environment variable
    api_key = x_api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Anthropic API key required. Pass it as 'x-api-key' header "
                   "or set ANTHROPIC_API_KEY environment variable.",
        )

    result = await nl_to_sql_and_execute(
        question=req.question,
        session=session,
        max_rows=req.max_rows,
        api_key=api_key,
    )

    # Log to history
    if result.error is None and req.session_id in _history:
        _history[req.session_id].append(
            QueryHistoryItem(
                question=req.question,
                sql=result.sql,
                row_count=result.row_count,
                timestamp=datetime.utcnow().isoformat(),
            )
        )

    return result


# ── Raw SQL query ──────────────────────────────────────────────────────────────

@router.post("/raw", response_model=QueryResult)
async def raw_query(req: SQLQueryRequest):
    """
    Execute a raw SQL query directly (no LLM involved).
    Used by the SQL editor panel in the frontend.
    """
    session = duck_store.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{req.session_id}' not found.")

    result = await execute_raw_sql(
        sql=req.sql,
        session=session,
        max_rows=req.max_rows,
    )

    if result.error is None and req.session_id in _history:
        _history[req.session_id].append(
            QueryHistoryItem(
                question=f"[RAW] {req.sql[:80]}",
                sql=req.sql,
                row_count=result.row_count,
                timestamp=datetime.utcnow().isoformat(),
            )
        )

    return result


# ── Query history ──────────────────────────────────────────────────────────────

@router.get("/history/{session_id}", response_model=QueryHistoryResponse)
def query_history(session_id: str):
    if not duck_store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return QueryHistoryResponse(
        session_id=session_id,
        history=_history.get(session_id, []),
    )


# ── Delete session ─────────────────────────────────────────────────────────────

@router.delete("/session/{session_id}")
def delete_session(session_id: str):
    if not duck_store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    duck_store.delete(session_id)
    _history.pop(session_id, None)
    return {"deleted": True, "session_id": session_id}
