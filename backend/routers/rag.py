"""
routers/rag.py
"""

from __future__ import annotations
import os
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException

from models.rag_schemas import (
    BuildIndexRequest,
    BuildIndexResponse,
    RAGChatRequest,
    RAGChatResponse,
)
from services.rag_service import build_index, rag_chat
from utils.vector_store import vector_store

router = APIRouter()


@router.post("/index", response_model=BuildIndexResponse)
async def create_index(
    req: BuildIndexRequest,
    x_api_key: Annotated[Optional[str], Header()] = None,
):
    # Index building may use external embedding provider if configured
    try:
        result = await build_index(
            file_ids=req.file_ids,
            table_names=req.table_names,
            extra_context=req.extra_context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Index build failed: {e}")

    if result.chunks_indexed == 0:
        raise HTTPException(
            status_code=404,
            detail="No data found for the provided file_ids. "
                   "Ensure files are uploaded and cleaned first.",
        )

    return result


@router.get("/index/{rag_session_id}")
def index_status(rag_session_id: str):
    idx = vector_store.get(rag_session_id)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"RAG session '{rag_session_id}' not found.")
    return {
        "rag_session_id": rag_session_id,
        "chunks_indexed": idx.chunk_count,
        "status": "ready",
    }


@router.post("/chat", response_model=RAGChatResponse)
async def chat(
    req: RAGChatRequest,
    x_api_key: Annotated[Optional[str], Header()] = None,
):
    if not vector_store.exists(req.rag_session_id):
        raise HTTPException(
            status_code=404,
            detail=f"RAG session '{req.rag_session_id}' not found. Build an index first.",
        )

    return await rag_chat(
        rag_session_id=req.rag_session_id,
        question=req.question,
        conversation_history=req.conversation_history,
    )


@router.delete("/index/{rag_session_id}")
def delete_index(rag_session_id: str):
    if not vector_store.exists(rag_session_id):
        raise HTTPException(status_code=404, detail=f"RAG session '{rag_session_id}' not found.")
    vector_store.delete(rag_session_id)
    return {"deleted": True, "rag_session_id": rag_session_id}
