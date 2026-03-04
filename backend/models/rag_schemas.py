"""
models/rag_schemas.py
──────────────────────
Pydantic models for the RAG chat engine.
"""

from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════
# INDEX BUILDING
# ══════════════════════════════════════════════════════════════════

class BuildIndexRequest(BaseModel):
    """
    Build a vector index from one or more cleaned datasets.
    Also accepts prior SQL query results and cleaning decisions
    so the RAG has full context of what happened to the data.
    """
    file_ids: List[str]
    table_names: Dict[str, str]         # file_id → table_name
    sql_session_id: Optional[str] = None
    # Optional extra context chunks to embed alongside the data
    extra_context: List[str] = Field(default_factory=list)


class BuildIndexResponse(BaseModel):
    rag_session_id: str
    chunks_indexed: int
    tables_indexed: List[str]
    status: str
    # column names per table — used by frontend to generate smart starter questions
    table_schemas: Dict[str, List[str]] = Field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════
# CHAT
# ══════════════════════════════════════════════════════════════════

class RAGChatRequest(BaseModel):
    rag_session_id: str
    question: str
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    # Each item: {"role": "user"|"assistant", "content": "..."}


class SourceChunk(BaseModel):
    content: str
    source: str             # e.g. "sales_2024 · rows 100-120"
    relevance_score: float  # cosine similarity 0-1


class RAGChatResponse(BaseModel):
    rag_session_id: str
    question: str
    answer: str
    source_chunks: List[SourceChunk]     # retrieved context shown to user
    insight_type: Literal[
        "descriptive",      # what happened
        "diagnostic",       # why it happened
        "predictive",       # what might happen
        "prescriptive",     # what to do
        "clarification",    # AI asked for more info
    ]
    suggested_sql: Optional[str] = None  # if a SQL query would answer this better
    follow_up_questions: List[str] = Field(default_factory=list)
