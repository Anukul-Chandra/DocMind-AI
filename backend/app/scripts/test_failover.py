"""
Manual integration test for automatic provider failover.

Verifies that ProviderManager automatically switches to the next provider
when one fails, and never raises while another provider is still available.
"""

import asyncio
import logging

from app.models.llm import LLMResponse
from app.services.llm.provider_manager import LLMUnavailableError, ProviderManager
from app.services.llm.providers.base import (
    BaseProvider,
    ProviderError,
    RateLimitError,
)


class OpenRouter(BaseProvider):
    """Mock OpenRouter provider that always fails as unavailable."""

    def __init__(self) -> None:
        self._model = "openrouter/mock"

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        raise ProviderError("OpenRouter unavailable (simulated)")


class Gemini(BaseProvider):
    """Mock Gemini provider with configurable failure behavior."""

    def __init__(self, failure: type[ProviderError] | None = RateLimitError) -> None:
        self._model = "gemini/mock"
        self._failure = failure

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        if self._failure is not None:
            raise self._failure("Gemini failed (simulated)")
        return "Failover succeeded via Gemini (simulated)."


class Groq(BaseProvider):
    """Mock Groq provider that always succeeds."""

    def __init__(self) -> None:
        self._model = "groq/mock"

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        return "Failover succeeded via Groq (simulated)."


def failure_label(exc: Exception | None) -> str:
    """Return a short, human-readable label for a provider failure.

    Args:
        exc: The exception raised by the provider, or None.

    Returns:
        A label describing the failure.
    """
    if isinstance(exc, RateLimitError):
        return "FAILED (Rate Limit)"
    return "FAILED"


async def run_scenario(
    scenario: str,
    providers: list[BaseProvider],
    expected_provider: str,
) -> bool:
    """Run a single failover scenario and print the attempt-by-attempt outcome.

    Args:
        scenario: A description of the scenario being tested.
        providers: The providers, in configured priority order.
        expected_provider: The provider expected to win, or None if all fail.

    Returns:
        True if the outcome matches the expectation.
    """
    print("=" * 60)
    print(f"Scenario: {scenario}")
    print("=" * 60)

    manager = ProviderManager(providers)

    try:
        response: LLMResponse | None = await manager.generate(
            prompt="What is automatic failover?"
        )
    except LLMUnavailableError:
        response = None

    if expected_provider is not None and response is None:
        print("FAIL: ProviderManager raised while a provider was still available")
        return False

    error_map = dict(manager.errors)
    winner = response.provider if response else None

    if response is not None:
        end = next(
            index
            for index, provider in enumerate(providers)
            if type(provider).__name__ == response.provider
        )
    else:
        end = len(providers) - 1

    for index in range(end + 1):
        provider = providers[index]
        name = type(provider).__name__
        print(f"\nAttempt {index + 1}:")
        print(name)
        if name == winner:
            print("SUCCESS")
        else:
            print(failure_label(error_map.get(name)))
        if index < end:
            print("\n↓")

    if response is None:
        print("\nProvider:")
        print("NONE (all providers failed)")
        return expected_provider is None

    print("\nProvider:")
    print(response.provider)
    print("\nResponse:")
    print(response.text)
    return response.provider == expected_provider


async def main() -> None:
    """Run all failover scenarios and report the overall result."""
    logging.getLogger("app.services.llm.provider_manager").setLevel(
        logging.CRITICAL
    )

    print("=" * 60)
    print("Failover Test")
    print("=" * 60)

    scenarios = [
        (
            "Scenario 1: OpenRouter unavailable -> Gemini succeeds",
            [OpenRouter(), Gemini(failure=None), Groq()],
            "Gemini",
        ),
        (
            "Scenario 2: Gemini RateLimitError -> Groq succeeds",
            [Gemini(), Groq()],
            "Groq",
        ),
        (
            "Scenario 3: OpenRouter unavailable + Gemini RateLimitError -> Groq succeeds",
            [OpenRouter(), Gemini(), Groq()],
            "Groq",
        ),
    ]

    passed = True
    for scenario, providers, expected in scenarios:
        passed = await run_scenario(scenario, providers, expected) and passed
        print()

    print("=" * 60)
    print(f"Failover Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
