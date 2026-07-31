"""Manual integration test for ProviderManager with OpenRouter, Gemini, and Groq."""

import asyncio

from app.services.llm.factory import build_provider_manager
from app.services.llm.provider_manager import LLMUnavailableError


async def main() -> None:
    manager = build_provider_manager()

    try:
        response = await manager.generate(
            prompt="Explain Python in one sentence."
        )
    except LLMUnavailableError as exc:
        print("\nAll providers failed:")
        for name, error in manager.errors:
            print(f"  {name}: {error}")
        return

    print("\nProvider:")
    print(response.provider)

    print("\nResponse:")
    print(response.text)

    print("\nErrors recorded:")
    if manager.errors:
        for name, error in manager.errors:
            print(f"  {name}: {error}")
    else:
        print("  (none)")


if __name__ == "__main__":
    asyncio.run(main())
