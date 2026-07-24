"""memory package — conversational memory and query history utilities

Lightweight in-memory history store for query history. Persisted to
`var/query_history.json` for basic durability.
"""
from .history import QueryHistoryStore

__all__ = ["QueryHistoryStore"]
