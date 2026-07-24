from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from .base import LLMProvider

logger = logging.getLogger("datagenie.llm.gemini")


class GeminiError(RuntimeError):
    """Raised when the Gemini API returns an error, a blocked prompt, or an empty response."""


class GeminiSettings:
    """Reads Gemini configuration from environment variables.

    Env vars:
        GEMINI_API_KEY   - required. Google AI Studio / Gemini API key.
        GEMINI_MODEL     - optional. Defaults to "gemini-flash-latest" (an
                           auto-updating alias Google points at its current
                           GA Flash model — this avoids hardcoding a model
                           string that gets deprecated for new API
                           keys/projects, as happened with gemini-2.5-flash).
                           Pin to a specific version (e.g. "gemini-3.6-flash")
                           for production if you want reproducible behavior.
        GEMINI_API_BASE  - optional. Defaults to the public Gemini REST base URL.
        GEMINI_TIMEOUT_S - optional. Request timeout in seconds (default 30).
    """

    def __init__(self):
        self.GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
        self.GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        self.GEMINI_API_BASE: str = os.getenv(
            "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
        )
        self.GEMINI_TIMEOUT_S: float = float(os.getenv("GEMINI_TIMEOUT_S", "30"))


class GeminiProvider(LLMProvider):
    """LLMProvider implementation backed by Google's Gemini API (generateContent).

    This talks to the real REST endpoint:
        POST {GEMINI_API_BASE}/models/{model}:generateContent?key=API_KEY

    A deterministic offline fallback (no network calls) is used only when the
    configured API key starts with "test_" — this keeps unit tests and local
    dev without credentials fast and hermetic, without silently masking a
    misconfigured production key the way the old "example" URL check did.
    """

    def __init__(self, settings: GeminiSettings | None = None, client: Optional[httpx.AsyncClient] = None):
        self.settings = settings or GeminiSettings()
        self._client = client or httpx.AsyncClient(timeout=self.settings.GEMINI_TIMEOUT_S)

    # ── Public API ──────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        response_mime_type: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if not self.settings.GEMINI_API_KEY:
            raise GeminiError("GEMINI_API_KEY is not set in environment")

        if self.settings.GEMINI_API_KEY.startswith("test_"):
            return self._offline_fallback(prompt)

        url = f"{self.settings.GEMINI_API_BASE}/models/{self.settings.GEMINI_MODEL}:generateContent"

        generation_config: Dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if response_mime_type:
            generation_config["responseMimeType"] = response_mime_type

        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }

        try:
            resp = await self._client.post(
                url,
                params={"key": self.settings.GEMINI_API_KEY},
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except httpx.RequestError as e:
            raise GeminiError(f"Failed to reach Gemini API: {e}") from e

        if resp.status_code != 200:
            detail = self._extract_error_message(resp)
            raise GeminiError(f"Gemini API error ({resp.status_code}): {detail}")

        data = resp.json()
        return self._extract_text(data)

    async def close(self) -> None:
        await self._client.aclose()

    # ── Internal helpers ──────────────────────────────────────────────

    def _extract_error_message(self, resp: httpx.Response) -> str:
        try:
            data = resp.json()
            return data.get("error", {}).get("message", resp.text)
        except Exception:
            return resp.text

    def _extract_text(self, data: Dict[str, Any]) -> str:
        """Pull the text out of a Gemini generateContent response.

        Raises GeminiError if the prompt was blocked or no candidates were
        returned, instead of silently returning an empty string (which would
        otherwise look like a valid-but-empty SQL generation to callers).
        """
        candidates: List[Dict[str, Any]] = data.get("candidates") or []

        if not candidates:
            feedback = data.get("promptFeedback", {})
            block_reason = feedback.get("blockReason")
            if block_reason:
                raise GeminiError(f"Prompt was blocked by Gemini safety filters: {block_reason}")
            raise GeminiError("Gemini API returned no candidates")

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason")

        parts = candidate.get("content", {}).get("parts", []) or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))

        if not text:
            if finish_reason == "SAFETY":
                raise GeminiError("Response was blocked by Gemini safety filters")
            if finish_reason == "MAX_TOKENS":
                raise GeminiError("Gemini response was truncated (hit max_tokens) before producing content")
            raise GeminiError(f"Gemini API returned an empty response (finishReason={finish_reason})")

        return text

    def _offline_fallback(self, prompt: str) -> str:
        """Deterministic canned responses for test_* API keys — no network I/O."""
        try:
            if "Available SQL tables" in prompt:
                m = re.search(r"\u2022\s+([a-zA-Z0-9_]+)\s*\(", prompt)
                table = m.group(1) if m else "data"
                sql = f"SELECT * FROM {table} LIMIT 10;"
                resp_obj = {
                    "sql": sql,
                    "explanation": "Auto-generated sample SQL.",
                    "assumptions": "",
                    "clarification_needed": "",
                }
                return json.dumps(resp_obj)

            sel = re.search(r"SELECT[\s\S]*?;", prompt, re.IGNORECASE)
            if sel:
                sql = sel.group(0)
                resp_obj = {
                    "sql": sql,
                    "explanation": "Repaired SQL (echo).",
                    "assumptions": "",
                    "clarification_needed": "",
                }
                return json.dumps(resp_obj)

            return "I am a local Gemini fallback: unable to call external API in test mode."
        except Exception:
            return ""