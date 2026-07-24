"""services/rag_service.py
RAG (Retrieval-Augmented Generation) chat service.

All LLM calls go through the `LLMService` abstraction backed by `GeminiProvider`.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

import numpy as np

from models.rag_schemas import (
    BuildIndexResponse,
    RAGChatResponse,
    SourceChunk,
)
from services.rag_chunker import build_chunks
from utils.session_store import store as df_store
from utils.vector_store import (
    RAGIndex,
    _pseudo_embed,
    vector_store,
)

from llm import llm_service


async def _embed_batch(texts: List[str], api_key: str) -> np.ndarray:
    return np.vstack([_pseudo_embed(t) for t in texts]).astype(np.float32)


async def build_index(
    file_ids: List[str],
    table_names: Dict[str, str],
    extra_context: List[str],
    api_key: str = "",
) -> BuildIndexResponse:
    idx = vector_store.create()
    tables_indexed = []
    table_schemas: Dict[str, List[str]] = {}
    total_chunks = 0

    for file_id in file_ids:
        df = df_store.load(file_id, copy=False)
        if df is None:
            continue
        table_name = table_names.get(file_id, file_id[:8])
        table_schemas[table_name] = list(df.columns)

        chunk_tuples = build_chunks(df, table_name, include_sample_rows=True)
        texts   = [c[0] for c in chunk_tuples]
        sources = [c[1] for c in chunk_tuples]

        if extra_context:
            texts.extend(extra_context)
            sources.extend(["user context"] * len(extra_context))

        vecs = await _embed_batch(texts, api_key)
        idx.add_chunks(texts, sources, vecs)

        tables_indexed.append(table_name)
        total_chunks += len(texts)

    return BuildIndexResponse(
        rag_session_id=idx.session_id,
        chunks_indexed=total_chunks,
        tables_indexed=tables_indexed,
        table_schemas=table_schemas,
        status="ready",
    )


def _build_rag_system_prompt(context_chunks: List[Tuple[str, str, float]]) -> str:
    context_text = "\n\n---\n\n".join(
        f"[Source: {source} | relevance: {score:.2f}]\n{text}"
        for text, source, score in context_chunks
    )
    return f"""You are DataGenie AI — an expert data analyst assistant.
Use ONLY the context below to answer. Never fabricate data.

CONTEXT:
{context_text}

RULES:
1. Ground every claim in the context. Be specific with actual values.
2. Use bullet points for multi-part answers.
3. End with 2-3 follow-up questions.

RESPOND WITH RAW JSON ONLY — no markdown, no code fences:
{{
  "answer": "<answer>",
  "insight_type": "<descriptive|diagnostic|predictive|prescriptive|clarification>",
  "suggested_sql": "<sql or empty string>",
  "follow_up_questions": ["<q1>", "<q2>", "<q3>"]
}}"""


_DIAGNOSTIC_KEYWORDS   = re.compile(r"\b(why|reason|cause|because|factor|explain|impact|affect|drive)\b", re.IGNORECASE)
_PREDICTIVE_KEYWORDS   = re.compile(r"\b(predict|forecast|will|future|trend|next|expect)\b", re.IGNORECASE)
_PRESCRIPTIVE_KEYWORDS = re.compile(r"\b(should|recommend|suggest|improve|action|strategy)\b", re.IGNORECASE)

def _detect_insight_type(question: str) -> str:
    if _PRESCRIPTIVE_KEYWORDS.search(question): return "prescriptive"
    if _PREDICTIVE_KEYWORDS.search(question):   return "predictive"
    if _DIAGNOSTIC_KEYWORDS.search(question):   return "diagnostic"
    return "descriptive"


async def rag_chat(
    rag_session_id: str,
    question: str,
    conversation_history: List[Dict[str, str]],
    api_key: str = "",
) -> RAGChatResponse:
    idx = vector_store.get(rag_session_id)
    if idx is None:
        return _error_response(rag_session_id, question, "RAG session not found.")

    q_vec    = _pseudo_embed(question)
    retrieved = idx.search(q_vec, top_k=8)
    if not retrieved:
        return _error_response(rag_session_id, question, "No relevant context found.")

    system_prompt = _build_rag_system_prompt(retrieved)

    # Build a single prompt string the Gemini provider can consume.
    convo_lines = []
    for m in conversation_history[-6:]:
        role = m.get("role", "user")
        content = m.get("content") or m.get("message") or ""
        convo_lines.append(f"{role.upper()}: {content}")
    convo_text = "\n".join(convo_lines)

    prompt = system_prompt + "\n\n" + convo_text + "\n\nUSER: " + question

    try:
        raw = await llm_service.generate_raw(prompt, temperature=0.0, max_tokens=1500)
    except Exception as e:
        return _error_response(rag_session_id, question, f"LLM provider error: {e}")

    # Aggressively extract JSON — provider may wrap it in markdown
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()

    # Try direct parse first
    data = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    if data is None:
        data = {
            "answer": raw,
            "insight_type": _detect_insight_type(question),
            "suggested_sql": "",
            "follow_up_questions": [],
        }

    # provider is centrally managed; no-op here

    source_chunks = [
        SourceChunk(content=text[:300] + ("..." if len(text) > 300 else ""), source=source, relevance_score=round(score, 3))
        for text, source, score in retrieved[:4]
    ]

    return RAGChatResponse(
        rag_session_id=rag_session_id,
        question=question,
        answer=data.get("answer", "").strip(),
        source_chunks=source_chunks,
        insight_type=data.get("insight_type", _detect_insight_type(question)),
        suggested_sql=data.get("suggested_sql", "").strip() or None,
        follow_up_questions=data.get("follow_up_questions", [])[:3],
    )


def _error_response(session_id: str, question: str, msg: str) -> RAGChatResponse:
    return RAGChatResponse(
        rag_session_id=session_id, question=question,
        answer=f"⚠️ {msg}", source_chunks=[],
        insight_type="clarification", suggested_sql=None, follow_up_questions=[],
    )