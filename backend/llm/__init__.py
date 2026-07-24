from .base import LLMProvider
from .gemini_provider import GeminiProvider
from .service import LLMService
from .utils import extract_sql

# Central LLM service instance used across the project. Services and routers
# should import `llm_service` from this module instead of instantiating
# providers directly. This ensures a single AI provider (Gemini) is used.
_default_provider = GeminiProvider()
llm_service = LLMService(_default_provider)

__all__ = ["LLMProvider", "GeminiProvider", "LLMService", "llm_service", "extract_sql"]
