import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.base import LLM, LLMError

T = TypeVar("T", bound=BaseModel)


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in output")
    return raw[start : end + 1]


def generate_structured(llm: LLM, system: str, prompt: str, schema: type[T], retries: int = 1) -> T:
    """Provider-agnostic structured output: schema in the prompt, validated with Pydantic, one retry."""
    full_system = (
        f"{system}\n\nReturn ONLY one JSON object that matches this JSON Schema. "
        f"No markdown, no commentary.\n{json.dumps(schema.model_json_schema())}"
    )
    last_error = ""
    for attempt in range(retries + 1):
        p = prompt if attempt == 0 else f"{prompt}\n\nYour previous output was invalid ({last_error}). Return only valid JSON."
        raw = llm.generate(full_system, p, json_mode=True)
        try:
            return schema.model_validate_json(_extract_json(raw))
        except (ValidationError, ValueError) as e:
            last_error = str(e).replace("\n", " ")[:300]
    raise LLMError("Model returned invalid structured output")
