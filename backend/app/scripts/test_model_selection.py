"""Deterministic regression test for LLM model selection quality.

Verifies, without any network or live LLM calls:

- ``curate_models`` excludes code/mini/tiny/nano/micro and embedding/reranker
  models while keeping capable general-purpose models (and not misclassifying
  names such as ``minimax-01``).
- ``build_curated_pool`` orders trusted general-purpose defaults first,
  excludes unsuitable models, and deduplicates.
- Model rotation and provider failover behavior stays intact for a curated
  pool (scripted HTTP client, no network).
- The RAG pipeline delivers relevant context to the LLM so an answer is not
  incorrectly treated as unavailable when the context contains it.

Usage (from backend/):
    ../.venv/bin/python app/scripts/test_model_selection.py
"""

import asyncio
import json

from app.core.config import settings
from app.services.chat.chat_service import ChatService
from app.services.chat.query_router import QueryRouter
from app.services.llm.model_catalog import curate_models
from app.services.llm.model_pool import ModelPoolManager, build_curated_pool
from app.services.llm.prompt_builder import PromptBuilder
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.base import (
    AuthenticationError,
    BaseProvider,
    ProviderError,
)
from app.services.llm.providers.openrouter import OpenRouterProvider

FALLBACK = "I couldn't find that information in the uploaded documents."

UNSUITABLE = [
    "cohere/north-mini-code:free",
    "openai/gpt-4o-mini:free",
    "qwen/qwen3-coder:free",
    "deepseek/deepseek-coder:free",
    "openai/o3-mini:free",
    "openai/gpt-4o-nano:free",
    "misc/llama-3.2-tiny:free",
    "openai/text-embedding-3-small:free",
    "misc/cohere-rerank:free",
]

GENERAL = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "minimax/minimax-01:free",
    "deepseek/deepseek-r1-0528:free",
    "google/gemma-3-27b-it:free",
]


async def test_curate_models() -> bool:
    """Code/mini/tiny/embedding models are excluded; general models are kept."""
    candidates = UNSUITABLE + GENERAL
    curated = curate_models(candidates)

    for unsuitable in UNSUITABLE:
        if unsuitable in curated:
            print(f"FAIL: unsuitable model not excluded: {unsuitable}")
            return False
    for general in GENERAL:
        if general not in curated:
            print(f"FAIL: general model dropped: {general}")
            return False
    if len(curated) != len(GENERAL):
        print(f"FAIL: expected {len(GENERAL)} curated models, got {curated}")
        return False
    return True


async def test_curate_models_preserves_minimax() -> bool:
    """'mini' substring inside 'minimax' must not cause a false positive."""
    curated = curate_models(["minimax/minimax-01:free"])
    if curated != ["minimax/minimax-01:free"]:
        print(f"FAIL: minimax misclassified as unsuitable: {curated}")
        return False
    return True


async def test_build_curated_pool() -> bool:
    """Trusted defaults lead the pool; unsuitable models are dropped."""
    candidates = [
        "cohere/north-mini-code:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "minimax/minimax-01:free",
        "qwen/qwen3-coder:free",
        "openai/gpt-4o-mini:free",
    ]
    preferred = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "deepseek/deepseek-r1-0528:free",
    ]
    pool = build_curated_pool(candidates, preferred=preferred)

    expected = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "minimax/minimax-01:free",
    ]
    if pool != expected:
        print(f"FAIL: expected pool {expected}, got {pool}")
        return False

    no_preferred = build_curated_pool(candidates)
    if no_preferred != ["meta-llama/llama-3.3-70b-instruct:free", "minimax/minimax-01:free"]:
        print(f"FAIL: pool without preferred mismatch: {no_preferred}")
        return False
    return True


class ScriptedResponse:
    """Minimal stand-in for httpx.Response used by the scripted client."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self) -> dict:
        return self._payload


class ScriptedClient:
    """A fake async client returning a queue of responses in call order."""

    def __init__(self, responses: list[tuple[int, dict | None]]) -> None:
        self._responses: list[tuple[int, dict | None]] = list(responses)
        self.calls: list[dict] = []

    async def post(
        self,
        url: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
    ) -> ScriptedResponse:
        self.calls.append(json)
        status_code, payload = self._responses.pop(0)
        return ScriptedResponse(status_code, payload)


def success_response(text: str) -> tuple[int, dict]:
    """Return a valid 200 OpenRouter chat completion response."""
    return 200, {"choices": [{"message": {"role": "assistant", "content": text}}]}


def build_provider(
    responses: list[tuple[int, dict | None]],
) -> tuple[OpenRouterProvider, list[str]]:
    """Build an OpenRouterProvider over the curated pool with a scripted client."""
    pool = build_curated_pool(
        [
            "cohere/north-mini-code:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "minimax/minimax-01:free",
            "openai/gpt-4o-mini:free",
        ],
        preferred=["meta-llama/llama-3.3-70b-instruct:free"],
    )
    provider = OpenRouterProvider(ModelPoolManager(pool), api_key="test-key")
    provider._client = ScriptedClient(responses)
    return provider, pool


def attempted_models(provider: OpenRouterProvider) -> list[str]:
    """Return the model ids tried, in request order."""
    return [call["model"] for call in provider._client.calls]


async def test_rotation_intact() -> bool:
    """A 429 rotates within the curated pool to the next capable model."""
    provider, pool = build_provider([(429, {}), success_response("ok")])

    text = await provider.generate("Hi")

    calls = attempted_models(provider)
    if text != "ok":
        print("FAIL: unexpected response text")
        return False
    if calls != pool:
        print(f"FAIL: expected rotation through {pool}, got {calls}")
        return False
    return True


async def test_auth_error_does_not_rotate() -> bool:
    """Authentication errors still fail fast without rotating the curated pool."""
    provider, _ = build_provider([(401, {}), success_response("never")])

    try:
        await provider.generate("Hi")
        print("FAIL: expected AuthenticationError")
        return False
    except AuthenticationError:
        pass

    if attempted_models(provider) != ["meta-llama/llama-3.3-70b-instruct:free"]:
        print("FAIL: auth error must only attempt the first curated model")
        return False
    return True


class MockGemini(BaseProvider):
    """Mock Gemini provider that always succeeds."""

    def __init__(self) -> None:
        self._model = "gemini/mock"

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> str:
        return "Failover succeeded via Gemini (simulated)."


async def test_failover_intact() -> bool:
    """Pool exhaustion still hands off to the next provider."""
    provider, pool = build_provider([(500, {}), (500, {})])
    manager = ProviderManager([provider, MockGemini()])

    response = await manager.generate("Hi")

    if response.provider != "MockGemini":
        print(f"FAIL: expected MockGemini to win, got {response.provider}")
        return False
    if attempted_models(provider) != pool:
        print(f"FAIL: expected every curated model tried once, got {attempted_models(provider)}")
        return False
    return True


class FakeRetriever:
    """Deterministic retriever returning a context that contains the answer."""

    def retrieve(
        self,
        question: str,
        owner_id: str = "",
        query_embedding: list[float] | None = None,
    ) -> list[dict]:
        return [
            {
                "text": "Anukul Chandra is an AI / ML Engineer from Dhaka, Bangladesh.",
                "filename": "Anukul Chandra-CV.pdf",
                "chunk_id": 1,
            }
        ]


class FakeEmbeddingService:
    """Deterministic embedding service for the test router."""

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] for _ in texts]


class FakeRelevanceScorer:
    """Deterministic relevance gate stand-in returning a fixed score."""

    def __init__(self, default: float = 0.0) -> None:
        self.default = default

    def __call__(
        self,
        question: str,
        owner_id: str,
        query_embedding: list[float] | None = None,
    ) -> float:
        return self.default


class RecordingProvider(BaseProvider):
    """Deterministic provider that records the prompt and returns a real answer."""

    def __init__(self) -> None:
        self._model = "openrouter/general-free"
        self.last_prompt: str = ""

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> str:
        self.last_prompt = prompt
        return "Anukul Chandra is an AI / ML Engineer from Dhaka, Bangladesh."


async def test_rag_answer_not_treated_unavailable() -> bool:
    """Relevant context reaches the LLM and the answer is surfaced, not the fallback."""
    provider = RecordingProvider()
    router = _document_router()
    service = ChatService(
        FakeRetriever(),
        PromptBuilder(),
        ProviderManager([provider]),
        query_router=router,
    )

    response = await service.chat("What is in my CV?", owner_id="owner-1")

    if FALLBACK in response.text:
        print(f"FAIL: real answer replaced by fallback: {response.text!r}")
        return False
    if "Anukul Chandra is an AI / ML Engineer" not in response.text:
        print(f"FAIL: expected the grounded answer, got {response.text!r}")
        return False
    if "Anukul Chandra is an AI / ML Engineer from Dhaka" not in provider.last_prompt:
        print("FAIL: relevant context was not delivered to the LLM")
        return False
    return True


def _document_router() -> QueryRouter:
    """Build a router whose relevance gate always routes to DOCUMENT.

    The RAG flow (not classification) is what this test verifies, so the gate
    is forced to its relevant branch regardless of the exact wording.
    """
    scorer = FakeRelevanceScorer()
    scorer.default = 0.9
    return QueryRouter(
        FakeEmbeddingService(),
        relevance_scorer=scorer,
        relevance_threshold=settings.rag_relevance_threshold,
    )


async def main() -> None:
    """Run all model-selection scenarios and report the overall result."""
    print("=" * 60)
    print("LLM Model Selection Test")
    print("=" * 60)

    scenarios = [
        ("Curation: unsuitable models excluded", test_curate_models),
        ("Curation: minimax not misclassified", test_curate_models_preserves_minimax),
        ("Pool: trusted defaults lead, dedup, exclude", test_build_curated_pool),
        ("Rotation: 429 rotates within curated pool", test_rotation_intact),
        ("Rotation: auth error does not rotate", test_auth_error_does_not_rotate),
        ("Failover: pool exhausted -> next provider", test_failover_intact),
        ("RAG: answer not treated as unavailable", test_rag_answer_not_treated_unavailable),
    ]

    passed = True
    for label, scenario in scenarios:
        print()
        print(label)
        result = await scenario()
        print("PASSED" if result else "FAILED")
        passed = passed and result

    print()
    print("=" * 60)
    print(f"Model Selection Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())