"""
utils/vector_store.py
──────────────────────
Lightweight in-memory vector store and pseudo-embedding utility.

No Chroma, no FAISS, no extra dependencies. Uses numpy for cosine
similarity — fast enough for datasets up to ~50,000 chunks.

For production scale (millions of rows), swap _search() to use
FAISS with an IVF index — the interface stays identical.

Architecture:
    RAGIndex
        ├── chunks: List[str]         — raw text
        ├── sources: List[str]        — source labels
        └── embeddings: np.ndarray    — shape (N, D)  [float32]
"""

from __future__ import annotations

import threading
import uuid
from typing import Dict, List, Optional, Tuple

import httpx
import numpy as np
from cachetools import TTLCache

# Max concurrently-cached RAG indexes and how long each lives before
# automatic eviction, so embeddings don't accumulate forever across
# the life of the process.
_MAXSIZE = 5
_TTL_SECONDS = 1800  # 30 minutes


# ══════════════════════════════════════════════════════════════════
# EMBEDDING CLIENT
# ══════════════════════════════════════════════════════════════════

VOYAGE_EMBED_URL = "https://api.voyageai.com/v1/embeddings"

# This module can use deterministic pseudo-embeddings for offline/demo
# use. Optionally configure a real embedding provider (Voyage AI) via
# `VOYAGE_API_KEY` to get production-quality embeddings.

def _pseudo_embed(text: str, dim: int = 512) -> np.ndarray:
    """
    Deterministic pseudo-embedding from text hashing.
    Captures term frequency signal — good enough for demo/dev.
    Replace with real embeddings in production.
    """
    words = text.lower().split()
    vec = np.zeros(dim, dtype=np.float32)

    for i, word in enumerate(words):
        # Simple hash-based projection
        h = hash(word) % dim
        h2 = (hash(word + "_2")) % dim
        vec[h] += 1.0 / (1 + i * 0.1)
        vec[h2] += 0.5
        # Bigrams
        if i < len(words) - 1:
            bigram = word + "_" + words[i + 1]
            hb = hash(bigram) % dim
            vec[hb] += 0.8

    # L2 normalise
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


async def _voyage_embed(text: str, api_key: str, dim: int = 512) -> np.ndarray:
    """
    Real semantic embedding via Voyage AI (Voyage embeddings).
    Falls back to pseudo_embed if API call fails.
    """
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                VOYAGE_EMBED_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "voyage-3",
                    "input": [text[:4000]],   # truncate to model limit
                },
            )
            resp.raise_for_status()
            data = resp.json()
            vec = np.array(data["data"][0]["embedding"], dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            return vec
    except Exception:
        # Graceful degradation
        return _pseudo_embed(text, dim)


# ══════════════════════════════════════════════════════════════════
# RAG INDEX
# ══════════════════════════════════════════════════════════════════

class RAGIndex:
    """Stores chunks + embeddings for one RAG session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.chunks: List[str] = []
        self.sources: List[str] = []
        self.embeddings: Optional[np.ndarray] = None   # (N, D) float32
        self._lock = threading.RLock()

    def add_chunks(self, texts: List[str], sources: List[str], vecs: np.ndarray) -> None:
        """Add pre-computed embeddings to the index."""
        with self._lock:
            self.chunks.extend(texts)
            self.sources.extend(sources)
            if self.embeddings is None:
                self.embeddings = vecs
            else:
                self.embeddings = np.vstack([self.embeddings, vecs])

    def search(self, query_vec: np.ndarray, top_k: int = 6) -> List[Tuple[str, str, float]]:
        """
        Cosine similarity search.
        Returns list of (chunk_text, source_label, score) sorted by relevance.
        """
        with self._lock:
            if self.embeddings is None or len(self.chunks) == 0:
                return []

            # query_vec shape: (D,)  →  (1, D)
            qv = query_vec.reshape(1, -1)
            # Embeddings already L2-normalised, so dot = cosine similarity
            scores = (self.embeddings @ qv.T).flatten()

            top_k = min(top_k, len(scores))
            top_idx = np.argpartition(scores, -top_k)[-top_k:]
            top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]

            return [
                (self.chunks[i], self.sources[i], float(scores[i]))
                for i in top_idx
            ]

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


# ══════════════════════════════════════════════════════════════════
# INDEX STORE (singleton)
# ══════════════════════════════════════════════════════════════════

class VectorStore:
    def __init__(self, maxsize: int = _MAXSIZE, ttl: int = _TTL_SECONDS):
        self._indexes: "TTLCache[str, RAGIndex]" = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.RLock()

    def create(self) -> RAGIndex:
        session_id = str(uuid.uuid4())
        idx = RAGIndex(session_id)
        with self._lock:
            self._indexes.expire()
            self._indexes[session_id] = idx
        return idx

    def get(self, session_id: str) -> Optional[RAGIndex]:
        with self._lock:
            self._indexes.expire()
            return self._indexes.get(session_id)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._indexes.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        with self._lock:
            self._indexes.expire()
            return session_id in self._indexes


vector_store = VectorStore()
