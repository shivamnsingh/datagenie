"""
routers/rag.py
───────────────
POST /api/rag/index          — build vector index from cleaned datasets
GET  /api/rag/index/{id}     — check index status + stats
POST /api/rag/chat           — ask a question, get grounded answer
DELETE /api/rag/index/{id}   — free the index
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


# ── Build index ────────────────────────────────────────────────────────────────

@router.post("/index", response_model=BuildIndexResponse)
async def create_index(
    req: BuildIndexRequest,
    x_api_key: Annotated[Optional[str], Header()] = None,
):
    """
    Chunk and embed all specified datasets into a searchable vector index.

    - Pass cleaned file_ids (from /api/clean/apply)
    - Optionally pass a sql_session_id to include query history context
    - Pass x-api-key header for real semantic embeddings (recommended)
    - Without API key, falls back to fast pseudo-embeddings (dev mode)
    """
    api_key = x_api_key or os.getenv("ANTHROPIC_API_KEY", "")

    try:
        result = await build_index(
            file_ids=req.file_ids,
            table_names=req.table_names,
            extra_context=req.extra_context,
            api_key=api_key,
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


# ── Index status ───────────────────────────────────────────────────────────────

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


# ── Chat ───────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=RAGChatResponse)
async def chat(
    req: RAGChatRequest,
    x_api_key: Annotated[Optional[str], Header()] = None,
):
    """
    Ask a natural language question about your data.

    The answer is grounded in retrieved context from the vector index —
    Claude cannot hallucinate values that aren't in your dataset.

    Pass conversation_history to maintain multi-turn context.
    """
    if not vector_store.exists(req.rag_session_id):
        raise HTTPException(
            status_code=404,
            detail=f"RAG session '{req.rag_session_id}' not found. Build an index first.",
        )

    api_key = x_api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Anthropic API key required. Pass as 'x-api-key' header "
                   "or set ANTHROPIC_API_KEY environment variable.",
        )

    return await rag_chat(
        rag_session_id=req.rag_session_id,
        question=req.question,
        conversation_history=req.conversation_history,
        api_key=api_key,
    )


# ── Delete index ───────────────────────────────────────────────────────────────

@router.delete("/index/{rag_session_id}")
def delete_index(rag_session_id: str):
    if not vector_store.exists(rag_session_id):
        raise HTTPException(status_code=404, detail=f"RAG session '{rag_session_id}' not found.")
    vector_store.delete(rag_session_id)
    return {"deleted": True, "rag_session_id": rag_session_id}
