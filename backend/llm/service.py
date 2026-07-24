from __future__ import annotations

import re
from typing import Optional

from .base import LLMProvider
from .utils import extract_sql


_FORBIDDEN_SQL_RE = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|MERGE)\b", re.IGNORECASE)


class SQLValidationError(ValueError):
    pass


class LLMService:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def generate_sql(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_mode: bool = True,
    ) -> dict:
        """Generate SQL from natural language prompt.

        When `json_mode` is True (default), the underlying provider is asked
        to constrain its output to valid JSON (Gemini's `responseMimeType`),
        which makes the downstream JSON parse in sql_service far more
        reliable than hoping the model obeys a "respond only in JSON"
        instruction in plain text.

        Returns dict: {raw: str, sql: Optional[str]}
        """
        raw = await self.provider.generate(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_mime_type="application/json" if json_mode else None,
        )
        sql = extract_sql(raw)
        return {"raw": raw, "sql": sql}

    async def generate_raw(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_mode: bool = True,
    ) -> str:
        """Generate raw text from the provider (no SQL extraction)."""
        return await self.provider.generate(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_mime_type="application/json" if json_mode else None,
        )

    async def close(self) -> None:
        try:
            await self.provider.close()
        except Exception:
            pass

    def validate_sql(self, sql: str) -> None:
        """Validate SQL is safe to execute — only SELECT queries allowed."""
        if not sql:
            raise SQLValidationError("No SQL to validate")

        if _FORBIDDEN_SQL_RE.search(sql):
            raise SQLValidationError("Destructive or non-SELECT statements are forbidden")

        if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
            raise SQLValidationError("Only SELECT queries are allowed")
