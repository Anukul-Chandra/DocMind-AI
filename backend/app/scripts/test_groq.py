"""
Manual integration test for the GroqProvider.
"""

import asyncio

from app.services.llm.providers.groq import GroqProvider


async def main() -> None:
    """Run the Groq provider integration test."""

    provider = GroqProvider()

    response = await provider.generate(
        prompt="Explain Python in one sentence."
    )

    print("=" * 60)
    print("Groq Provider Test")
    print("=" * 60)

    # If provider returns LLMResponse
    if hasattr(response, "provider"):
        print(f"Provider : {response.provider}")
        print(f"Model    : {response.model}")
        print(f"Response : {response.content}")
    else:
        # If provider currently returns str
        print(response)


if __name__ == "__main__":
    asyncio.run(main())