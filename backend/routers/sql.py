"""
routers/sql.py
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException

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

_history: dict[str, list] = {}


# -----------------------------------------------------------------------------
# Create SQL Session
# -----------------------------------------------------------------------------

@router.post("/session", response_model=SQLSessionInfo)
def create_session(req: RegisterTablesRequest):
    session = duck_store.create()

    for table in req.tables:
        df = df_store.load(table.file_id)

        if df is None:
            duck_store.delete(session.session_id)
            raise HTTPException(
                status_code=404,
                detail=f"File '{table.file_id}' not found."
            )

        session.register(table.table_name, df, table.file_id)

    _history[session.session_id] = []

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

    # -------------------------------------------------------------------------
    # API Key
    # -------------------------------------------------------------------------

    api_key = (x_api_key or "").strip()

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Please enter your Groq API key."
        )

    if not api_key.startswith("gsk_"):
        raise HTTPException(
            status_code=401,
            detail="Invalid Groq API key format."
        )

    print("=" * 60)
    print("Groq key received:", api_key[:10] + "...")
    print("Length:", len(api_key))
    print("=" * 60)

    result = await nl_to_sql_and_execute(
        question=req.question,
        session=session,
        max_rows=req.max_rows,
        api_key=api_key,
    )

    if result.error is None:

        _history.setdefault(req.session_id, []).append(
            QueryHistoryItem(
                question=req.question,
                sql=result.sql,
                row_count=result.row_count,
                timestamp=datetime.utcnow().isoformat(),
            )
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

        _history.setdefault(req.session_id, []).append(
            QueryHistoryItem(
                question=f"[RAW] {req.sql[:100]}",
                sql=req.sql,
                row_count=result.row_count,
                timestamp=datetime.utcnow().isoformat(),
            )
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

    return QueryHistoryResponse(
        session_id=session_id,
        history=_history.get(session_id, []),
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
    _history.pop(session_id, None)

    return {
        "deleted": True,
        "session_id": session_id,
    }