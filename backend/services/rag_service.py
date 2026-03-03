"""
services/rag_service.py
────────────────────────
The RAG brain. Two responsibilities:

  1. build_index()  — chunk DataFrames → embed → store in VectorStore
  2. rag_chat()     — retrieve relevant chunks → augment Claude prompt → answer

The key insight: we don't just embed raw rows.
We embed STATISTICS, DISTRIBUTIONS, CORRELATIONS, and SAMPLE ROWS.
This lets Claude answer both factual ("who has highest sales?") AND
analytical ("why is the North region underperforming?") questions.

Conversation memory is maintained per session — each turn sees
the last 6 exchanges so Claude can answer follow-ups naturally.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Dict, List, Optional, Tuple

import httpx
import numpy as np
import pandas as pd

from models.rag_schemas import (
    BuildIndexResponse,
    RAGChatResponse,
    SourceChunk,
)
from services.rag_chunker import build_chunks
from utils.session_store import store as df_store
from utils.vector_store import (
    RAGIndex,
    _claude_embed,
    _pseudo_embed,
    vector_store,
)


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-sonnet-4-20250514"


# ══════════════════════════════════════════════════════════════════
# INDEX BUILDING
# ══════════════════════════════════════════════════════════════════

async def _embed_batch(
    texts: List[str],
    api_key: str,
) -> np.ndarray:
    """
    Embed a list of texts. Uses real embeddings if api_key provided,
    otherwise falls back to fast pseudo-embeddings.
    """
    if not api_key:
        return np.vstack([_pseudo_embed(t) for t in texts]).astype(np.float32)

    # Embed concurrently in batches of 20
    batch_size = 20
    all_vecs = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vecs = await asyncio.gather(*[_claude_embed(t, api_key) for t in batch])
        all_vecs.extend(vecs)

    return np.vstack(all_vecs).astype(np.float32)


async def build_index(
    file_ids: List[str],
    table_names: Dict[str, str],
    extra_context: List[str],
    api_key: str = "",
) -> BuildIndexResponse:
    """
    Build a RAG index from a set of DataFrames.
    Returns a rag_session_id to use in subsequent chat calls.
    """
    idx = vector_store.create()
    tables_indexed = []
    total_chunks = 0

    for file_id in file_ids:
        df = df_store.load(file_id)
        if df is None:
            continue
        table_name = table_names.get(file_id, file_id[:8])

        # Generate all chunk types
        chunk_tuples = build_chunks(df, table_name, include_sample_rows=True)
        texts = [c[0] for c in chunk_tuples]
        sources = [c[1] for c in chunk_tuples]

        # Add extra context chunks
        if extra_context:
            texts.extend(extra_context)
            sources.extend(["user context"] * len(extra_context))

        # Embed
        vecs = await _embed_batch(texts, api_key)
        idx.add_chunks(texts, sources, vecs)

        tables_indexed.append(table_name)
        total_chunks += len(texts)

    return BuildIndexResponse(
        rag_session_id=idx.session_id,
        chunks_indexed=total_chunks,
        tables_indexed=tables_indexed,
        status="ready",
    )


# ══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════

def _build_rag_system_prompt(context_chunks: List[Tuple[str, str, float]]) -> str:
    """
    Build the system prompt with retrieved context injected.
    """
    context_text = "\n\n---\n\n".join(
        f"[Source: {source} | relevance: {score:.2f}]\n{text}"
        for text, source, score in context_chunks
    )

    return f"""You are DataGenie AI — an expert data analyst assistant.
You have been given context retrieved from the user's actual dataset.
Use ONLY the information in the context below to answer questions.

If the context doesn't contain enough information to answer confidently,
say so clearly and suggest what SQL query might get the answer.

CONTEXT FROM DATASET:
{context_text}

RESPONSE RULES:
1. Ground every claim in the context. Never fabricate numbers or patterns.
2. Be specific — cite actual values from the data (e.g. "Region A had 2,341 sales").
3. For "why" questions, reason from correlations and distributions in the context.
4. Keep answers concise but complete — use bullet points for multi-part answers.
5. If you spot something interesting the user didn't ask about, mention it briefly.
6. End with 2-3 sharp follow-up questions that would deepen the analysis.

RESPONSE FORMAT — always respond with valid JSON:
{{
  "answer": "<your full analytical answer>",
  "insight_type": "<one of: descriptive|diagnostic|predictive|prescriptive|clarification>",
  "suggested_sql": "<a SQL query if one would answer this better, or empty string>",
  "follow_up_questions": ["<question 1>", "<question 2>", "<question 3>"]
}}

No markdown, no code fences. Raw JSON only."""


# ══════════════════════════════════════════════════════════════════
# INTENT DETECTION
# ══════════════════════════════════════════════════════════════════

_DIAGNOSTIC_KEYWORDS = re.compile(
    r"\b(why|reason|cause|because|factor|explain|impact|affect|influenc|drive|lead to)\b",
    re.IGNORECASE,
)
_PREDICTIVE_KEYWORDS = re.compile(
    r"\b(predict|forecast|will|future|trend|next|expect|project|estimate)\b",
    re.IGNORECASE,
)
_PRESCRIPTIVE_KEYWORDS = re.compile(
    r"\b(should|recommend|suggest|improve|optimis|optim|action|strategy|what to do)\b",
    re.IGNORECASE,
)


def _detect_insight_type(question: str) -> str:
    if _PRESCRIPTIVE_KEYWORDS.search(question):
        return "prescriptive"
    if _PREDICTIVE_KEYWORDS.search(question):
        return "predictive"
    if _DIAGNOSTIC_KEYWORDS.search(question):
        return "diagnostic"
    return "descriptive"


# ══════════════════════════════════════════════════════════════════
# RAG CHAT
# ══════════════════════════════════════════════════════════════════

async def rag_chat(
    rag_session_id: str,
    question: str,
    conversation_history: List[Dict[str, str]],
    api_key: str = "",
) -> RAGChatResponse:
    """
    Retrieve relevant chunks → augment Claude prompt → generate answer.
    """
    idx = vector_store.get(rag_session_id)
    if idx is None:
        return _error_response(rag_session_id, question, "RAG session not found.")

    # ── Step 1: Embed the question ──────────────────────────────
    if api_key:
        q_vec = await _claude_embed(question, api_key)
    else:
        q_vec = _pseudo_embed(question)

    # ── Step 2: Retrieve top-k chunks ───────────────────────────
    retrieved = idx.search(q_vec, top_k=8)

    if not retrieved:
        return _error_response(rag_session_id, question, "No relevant context found in the indexed data.")

    # ── Step 3: Build augmented prompt ──────────────────────────
    system_prompt = _build_rag_system_prompt(retrieved)

    # Include last 6 turns of conversation history
    history_tail = conversation_history[-6:]
    messages = [
        *history_tail,
        {"role": "user", "content": question},
    ]

    # ── Step 4: Call Claude ──────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key or os.getenv("ANTHROPIC_API_KEY", ""),
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 1500,
                    "system": system_prompt,
                    "messages": messages,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["content"][0]["text"]
    except httpx.HTTPStatusError as e:
        return _error_response(
            rag_session_id, question,
            f"Claude API error {e.response.status_code}: {e.response.text}",
        )
    except Exception as e:
        return _error_response(rag_session_id, question, f"API call failed: {e}")

    # ── Step 5: Parse response ───────────────────────────────────
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat entire response as plain answer
        data = {
            "answer": raw,
            "insight_type": _detect_insight_type(question),
            "suggested_sql": "",
            "follow_up_questions": [],
        }

    answer = data.get("answer", "").strip()
    insight_type = data.get("insight_type", _detect_insight_type(question))
    suggested_sql = data.get("suggested_sql", "").strip()
    follow_ups = data.get("follow_up_questions", [])[:3]

    # ── Step 6: Build source chunks for citation UI ──────────────
    source_chunks = [
        SourceChunk(
            content=text[:300] + ("..." if len(text) > 300 else ""),
            source=source,
            relevance_score=round(score, 3),
        )
        for text, source, score in retrieved[:4]   # show top 4 in UI
    ]

    return RAGChatResponse(
        rag_session_id=rag_session_id,
        question=question,
        answer=answer,
        source_chunks=source_chunks,
        insight_type=insight_type,
        suggested_sql=suggested_sql or None,
        follow_up_questions=follow_ups,
    )


# ── Helper ─────────────────────────────────────────────────────────────────────

def _error_response(session_id: str, question: str, msg: str) -> RAGChatResponse:
    return RAGChatResponse(
        rag_session_id=session_id,
        question=question,
        answer=f"⚠️ {msg}",
        source_chunks=[],
        insight_type="clarification",
        suggested_sql=None,
        follow_up_questions=[],
    )
