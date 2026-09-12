"""Focused test proving the FastAPI startup lifespan warms the cached chat
dependency graph so the first user request does not pay initialization cost.

The real initialization chain (EmbeddingService, ProviderManager, model catalog
discovery, FAISS/metadata stores) is exercised through the existing
``@lru_cache`` dependency functions. Network-bound and heavy native pieces
(``build_provider_manager`` and the ``EmbeddingService`` constructor) are
replaced with lightweight doubles so the test stays hermetic and fast; the
point under test is that ``lifespan`` invokes ``get_chat_service`` and that the
result is cached and reused.
"""

import asyncio
import os
from unittest import mock

# Settings are constructed at import time and require a JWT secret; provide a
# non-secret value before importing any application module, mirroring the
# pattern used in app/scripts/test_config_validation.py.
os.environ.setdefault("JWT_SECRET", "test-secret-for-startup-warmup")

from app.api.dependencies import (  # noqa: E402
    get_chat_service,
    get_embedding_service,
)
from app.main import app, lifespan  # noqa: E402
from app.services.llm.provider_manager import ProviderManager  # noqa: E402
import app.services.embedding as embedding_mod  # noqa: E402
import app.services.llm.factory as factory_mod  # noqa: E402


class _FakeEmbeddingService:
    """Drop-in double for EmbeddingService that avoids torch/model loading."""

    def __init__(self) -> None:
        pass

    def get_embedding_dimension(self) -> int:
        return 384

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 384 for _ in texts]


def _build_provider_manager():
    return ProviderManager([mock.MagicMock()])


async def _drive_lifespan() -> None:
    async with lifespan(app):
        pass


def test_startup_warmup_populates_chat_service_cache(monkeypatch):
    monkeypatch.setattr(
        embedding_mod, "EmbeddingService", _FakeEmbeddingService, raising=True
    )
    monkeypatch.setattr(
        factory_mod,
        "build_provider_manager",
        _build_provider_manager,
        raising=True,
    )

    for cached_fn in (get_chat_service, get_embedding_service):
        cached_fn.cache_clear()

    assert get_chat_service.cache_info().currsize == 0

    asyncio.run(_drive_lifespan())

    assert get_chat_service.cache_info().currsize == 1
    assert get_embedding_service.cache_info().currsize == 1

    first = get_chat_service()
    second = get_chat_service()
    assert first is second
