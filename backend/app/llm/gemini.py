import logging
import time

from app.llm.base import LLMError, LLMUnavailable

log = logging.getLogger("bizos.llm")


class GeminiLLM:
    def __init__(self, api_key: str, model: str):
        from google import genai

        from google.genai import types as _t

        # without a timeout a blocked network makes the chat hang on "Typing..." for minutes
        self._client = genai.Client(api_key=api_key, http_options=_t.HttpOptions(timeout=25000))
        self._model = model

    def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> str:
        from google.genai import errors, types

        kwargs: dict = {"system_instruction": system, "max_output_tokens": 4096}
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        config = types.GenerateContentConfig(**kwargs)

        last: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._client.models.generate_content(model=self._model, contents=prompt, config=config)
                text = resp.text
                if not text:
                    raise LLMError("Model returned an empty response (it may have been blocked)")
                return text
            except errors.ClientError as e:
                code = getattr(e, "code", None)
                log.warning("Gemini client error %s: %s", code, str(e)[:300])
                if code == 429:  # free tier rate limit: back off and retry
                    last = e
                    time.sleep(2 * (attempt + 1))
                    continue
                if code in (400, 401, 403):
                    raise LLMUnavailable("Gemini rejected the request. Check LLM_API_KEY in backend/.env.") from e
                if code == 404:
                    raise LLMUnavailable(f"Model '{self._model}' was not found. Check LLM_MODEL in backend/.env.") from e
                raise LLMError(f"Gemini error {code}") from e
            except errors.ServerError as e:
                log.warning("Gemini server error: %s", str(e)[:300])
                last = e
                time.sleep(1 + attempt)
            except (LLMError, LLMUnavailable):
                raise
            except Exception as e:  # network down, DNS blocked, timeout
                log.warning("Gemini unreachable: %s", str(e)[:300])
                raise LLMUnavailable("Cannot reach Gemini from this network. Check your internet or DNS.") from e
        raise LLMUnavailable("Gemini is rate limiting or unavailable right now. Wait a minute and try again.") from last
