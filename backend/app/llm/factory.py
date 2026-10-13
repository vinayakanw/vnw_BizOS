from app.core.config import settings
from app.llm.base import LLM, LLMUnavailable

_override: LLM | None = None
_llm: LLM | None = None


def set_llm(llm: LLM | None) -> None:
    """Tests inject a scripted model here."""
    global _override
    _override = llm


def get_llm() -> LLM:
    global _llm
    if _override is not None:
        return _override
    if _llm is None:
        if settings.llm_provider == "gemini":
            if not settings.llm_api_key:
                raise LLMUnavailable("LLM_API_KEY is not set. Add it to backend/.env and restart the server.")
            from app.llm.gemini import GeminiLLM

            _llm = GeminiLLM(settings.llm_api_key, settings.llm_model)
        else:
            raise LLMUnavailable(f"Unknown LLM_PROVIDER '{settings.llm_provider}'")
    return _llm
