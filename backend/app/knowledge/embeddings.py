import math
import re
import threading
import zlib
from typing import Protocol

from app.core.config import settings


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """Local CPU embeddings. The model downloads once (~130 MB) on first use."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()


class FakeEmbedder:
    """Deterministic hashed bag-of-words. Only for tests, no model needed."""

    def __init__(self, dim: int):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"\w+", text.lower()):
            v[zlib.crc32(tok.encode()) % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


_embedder: Embedder | None = None
_lock = threading.Lock()


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                if settings.embedding_provider == "fake":
                    _embedder = FakeEmbedder(settings.embedding_dim)
                elif settings.embedding_provider == "local":
                    _embedder = FastEmbedEmbedder(settings.embedding_model)
                else:
                    raise RuntimeError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider}")
    return _embedder
