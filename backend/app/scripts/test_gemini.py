"""
Manual integration test for the GeminiProvider.
"""

import asyncio

from app.core.config import settings
from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    InvalidResponseError,
    ProviderError,
    RateLimitError,
)
from app.services.llm.providers.gemini import GeminiProvider


async def main() -> None:
    """Run the Gemini provider integration test."""

    if not settings.gemini_api_key:
        print("Gemini API key is missing. Set GEMINI_API_KEY and try again.")
        return

    provider = GeminiProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )

    try:
        response = await provider.generate(
            prompt="What is Python?",
        )
    except AuthenticationError as exc:
        print("Gemini authentication failed:", exc)
        return
    except RateLimitError as exc:
        print("Gemini rate limit exceeded:", exc)
        return
    except APIError as exc:
        print(f"Gemini API error (HTTP {exc.status_code}):", exc)
        return
    except InvalidResponseError as exc:
        print("Gemini returned an invalid response:", exc)
        return
    except ProviderError as exc:
        print("Gemini request failed:", exc)
        return

    print("=" * 60)
    print("Gemini Provider Test")
    print("=" * 60)

    print("\nModel:")
    print(provider.model)

    print("\nResponse:")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
