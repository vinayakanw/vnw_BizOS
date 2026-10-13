from typing import Protocol


class LLMError(Exception):
    """The model call failed or returned something unusable."""


class LLMUnavailable(LLMError):
    """Misconfigured key, rate limit, or provider outage. Safe to show to the operator."""


class LLM(Protocol):
    def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> str: ...
