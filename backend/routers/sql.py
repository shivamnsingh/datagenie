"""
routers/sql.py
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException
from memory.history import QueryHistoryStore

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

# Persisted query history store
_history_store = QueryHistoryStore()


# -----------------------------------------------------------------------------
# Create SQL Session
# -----------------------------------------------------------------------------

@router.post("/session", response_model=SQLSessionInfo)
def create_session(req: RegisterTablesRequest):
    session = duck_store.create()

    for table in req.tables:
        df = df_store.load(table.file_id, copy=False)

        # If the DataFrame isn't in the in-memory cache, try loading a persisted
        # CSV written at ingest time at `.data/files/{file_id}.csv`. This makes
        # session creation robust to process restarts or reloads.
        if df is None:
            try:
                from pathlib import Path
                import pandas as pd
                p = Path('.data') / 'files' / f"{table.file_id}.csv"
                if p.exists():
                    df = pd.read_csv(p)
                    df_store.save(table.file_id, df)
                else:
                    duck_store.delete(session.session_id)
                    raise HTTPException(
                        status_code=404,
                        detail=f"File '{table.file_id}' not found."
                    )
            except HTTPException:
                raise
            except Exception:
                duck_store.delete(session.session_id)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to load file '{table.file_id}'."
                )

        session.register(table.table_name, df, table.file_id)

    # persist initial session history via the QueryHistoryStore (no in-memory history)
    # historically we used an in-memory _history; keep compatibility by ensuring
    # the persisted store has no items for this session yet.
    # (No-op — QueryHistoryStore will create entries on first add.)

    return session.to_session_info()


# -----------------------------------------------------------------------------
# Get Session
# -----------------------------------------------------------------------------

@router.get("/session/{session_id}", response_model=SQLSessionInfo)
def get_session(session_id: str):

    session = duck_store.get(session_id)

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    return session.to_session_info()


# -----------------------------------------------------------------------------
# Natural Language → SQL
# -----------------------------------------------------------------------------

@router.post("/query", response_model=QueryResult)
async def nl_query(
    req: NLQueryRequest,
    x_api_key: Annotated[Optional[str], Header()] = None,
):

    session = duck_store.get(req.session_id)

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    result = await nl_to_sql_and_execute(
        question=req.question,
        session=session,
        max_rows=req.max_rows,
    )

    if result.error is None:
        # Persist to history store
        _history_store.add(
            req.session_id,
            req.question,
            result.sql,
            result.execution_time_ms,
            result.row_count,
        )

    return result


# -----------------------------------------------------------------------------
# Raw SQL
# -----------------------------------------------------------------------------

@router.post("/raw", response_model=QueryResult)
async def raw_query(req: SQLQueryRequest):

    session = duck_store.get(req.session_id)

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    result = await execute_raw_sql(
        sql=req.sql,
        session=session,
        max_rows=req.max_rows,
    )

    if result.error is None:
        _history_store.add(
            req.session_id,
            f"[RAW] {req.sql[:100]}",
            req.sql,
            result.execution_time_ms,
            result.row_count,
        )

    return result


# -----------------------------------------------------------------------------
# History
# -----------------------------------------------------------------------------

@router.get("/history/{session_id}", response_model=QueryHistoryResponse)
def query_history(session_id: str):

    if not duck_store.exists(session_id):
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )
    items = _history_store.list(limit=200, session_id=session_id)
    # map to API model shape
    history = [
        QueryHistoryItem(
            question=i.question,
            sql=i.sql,
            row_count=i.rows_returned,
            timestamp=i.timestamp,
        )
        for i in items
    ]

    return QueryHistoryResponse(
        session_id=session_id,
        history=history,
    )


# -----------------------------------------------------------------------------
# Delete Session
# -----------------------------------------------------------------------------

@router.delete("/session/{session_id}")
def delete_session(session_id: str):

    if not duck_store.exists(session_id):
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    duck_store.delete(session_id)
    # remove persisted items for this session
    # simple approach: rewrite store without this session's items
    remaining = [i for i in _history_store.list(limit=1000) if getattr(i, 'session_id', None) != session_id]
    # persist remaining
    try:
        from pathlib import Path
        import json
        p = Path('.data') / 'query_history.json'
        with p.open('w', encoding='utf-8') as f:
            json.dump([{
                'session_id': it.session_id,
                'timestamp': it.timestamp,
                'question': it.question,
                'sql': it.sql,
                'execution_time_ms': it.execution_time_ms,
                'rows_returned': it.rows_returned,
            } for it in remaining], f, indent=2)
    except Exception:
        pass

    return {
        "deleted": True,
        "session_id": session_id,
    }