"""Deterministic tests for the refreshed Gemini and Groq fallback models.

Verifies without network access:

- tracked defaults equal the live-provider-verified model ids
  (gemini-3.6-flash / openai/gpt-oss-120b; the retired
  gemini-2.0-flash and llama-3.3-70b-versatile must never return)
- GeminiProvider/GroqProvider construct correctly and pass the configured
  model id through to the SDK call
- existing response parsing still works
- API errors map onto the existing provider error architecture

Usage (from backend/):
    PYTHONPATH=. ../.venv/bin/python app/scripts/test_fallback_models.py
"""

import asyncio
import sys

from app.core.config import settings
from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    InvalidResponseError,
    RateLimitError,
)
from app.services.llm.providers.gemini import GeminiProvider
from app.services.llm.providers.groq import GroqProvider

VERIFIED_GEMINI_MODEL = "gemini-3.6-flash"
VERIFIED_GROQ_MODEL = "openai/gpt-oss-120b"
RETIRED_MODELS = {"gemini-2.0-flash", "llama-3.3-70b-versatile"}


# --- fakes -------------------------------------------------------------------

class FakeGeminiResponse:
    def __init__(self, text):
        self.text = text


class FakeGeminiAioModels:
    """Records generate_content kwargs and scripts one result/exception."""

    def __init__(self, result):
        self._result = result
        self.calls: list[dict] = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeGeminiClient:
    def __init__(self, result):
        self.aio = type("Aio", (), {})()
        self.aio.models = FakeGeminiAioModels(result)


class FakeGroqCompletions:
    def __init__(self, result):
        self._result = result
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result

        class _Msg:
            content = getattr(self._result, "content", None)

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


class FakeGroqChat:
    def __init__(self, result):
        self.completions = FakeGroqCompletions(result)


class FakeGroqClient:
    def __init__(self, result):
        self.chat = FakeGroqChat(result)


class FakeGeminiClientError(Exception):
    """Stand-in carrying only what the provider mapping reads (``code``)."""

    def __init__(self, code, message="boom"):
        self.code = code
        super().__init__(message)


def gemini_error(code: int) -> Exception:
    """Build a real google-genai client/server error with the given code."""
    from google.genai import errors as genai_errors

    cls = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    return cls(code, "boom")


class FakeAPIStatusError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"status {status_code}")


def make_gemini(result) -> tuple[GeminiProvider, FakeGeminiAioModels]:
    provider = GeminiProvider(api_key="test-key", model=VERIFIED_GEMINI_MODEL)
    fake_client = FakeGeminiClient(result)
    provider._client = fake_client
    return provider, fake_client.aio.models


def make_groq(result) -> tuple[GroqProvider, FakeGroqCompletions]:
    provider = GroqProvider(api_key="test-key", model=VERIFIED_GROQ_MODEL)
    fake_client = FakeGroqClient(result)
    provider._client = fake_client
    return provider, fake_client.chat.completions


# --- checks ------------------------------------------------------------------

def test_tracked_defaults_are_verified_models() -> bool:
    """The tracked configuration points at the verified, non-retired ids."""
    if settings.gemini_model != VERIFIED_GEMINI_MODEL:
        print(f"FAIL: gemini default is {settings.gemini_model!r}, "
              f"expected {VERIFIED_GEMINI_MODEL!r}")
        return False
    if settings.groq_model != VERIFIED_GROQ_MODEL:
        print(f"FAIL: groq default is {settings.groq_model!r}, "
              f"expected {VERIFIED_GROQ_MODEL!r}")
        return False
    if {settings.gemini_model, settings.groq_model} & RETIRED_MODELS:
        print("FAIL: a retired model id returned to the defaults")
        return False
    return True


async def test_gemini_constructs_and_passes_model() -> bool:
    """Construction works offline and the model id reaches the SDK call."""
    text = "OK from Gemini."
    provider, fake = make_gemini(FakeGeminiResponse(text))

    out = await provider.generate("Hi")

    if out != text:
        print(f"FAIL: unexpected Gemini output {out!r}")
        return False
    if provider.model != VERIFIED_GEMINI_MODEL:
        print(f"FAIL: provider.model is {provider.model!r}")
        return False
    if not fake.calls or fake.calls[0].get("model") != VERIFIED_GEMINI_MODEL:
        print(f"FAIL: SDK call got model={fake.calls[0].get('model')!r}"
              if fake.calls else "FAIL: SDK was not called")
        return False
    return True


async def test_gemini_error_mapping() -> bool:
    """Gemini SDK errors keep mapping onto the shared error architecture."""
    cases = [
        (gemini_error(400), AuthenticationError),
        (gemini_error(401), AuthenticationError),
        (gemini_error(403), AuthenticationError),
        (gemini_error(429), RateLimitError),
        (gemini_error(500), APIError),
    ]
    for exc, expected in cases:
        provider, _ = make_gemini(exc)
        try:
            await provider.generate("Hi")
            print(f"FAIL: code {exc.code} did not raise")
            return False
        except expected:
            continue
        except Exception as e:  # noqa: BLE001
            print(f"FAIL: code {exc.code} raised {type(e).__name__}, "
                  f"expected {expected.__name__}")
            return False

    provider, _ = make_gemini(FakeGeminiResponse(None))
    try:
        await provider.generate("Hi")
        print("FAIL: empty Gemini response did not raise InvalidResponseError")
        return False
    except InvalidResponseError:
        return True


async def test_groq_constructs_and_parses() -> bool:
    """Construction works offline, the model id is passed, parsing holds."""
    provider, fake = make_groq(type("MsgStub", (), {"content": "OK"})())

    out = await provider.generate("Hi")

    if out != "OK":
        print(f"FAIL: unexpected Groq output {out!r}")
        return False
    if provider.model != VERIFIED_GROQ_MODEL:
        print(f"FAIL: provider.model is {provider.model!r}")
        return False
    if not fake.calls or fake.calls[0].get("model") != VERIFIED_GROQ_MODEL:
        print("FAIL: configured model id not passed to the SDK call")
        return False
    return True


async def test_groq_error_mapping() -> bool:
    """Groq SDK errors keep mapping onto the shared error architecture."""
    from groq import (
        APIStatusError as GroqAPIStatusError,
        AuthenticationError as GroqAuthError,
        RateLimitError as GroqRateLimitError,
    )

    class ScriptedAuthError(GroqAuthError):
        def __init__(self) -> None:
            Exception.__init__(self, "bad key")

    class ScriptedRateLimitError(GroqRateLimitError):
        def __init__(self) -> None:
            Exception.__init__(self, "limited")

    class ScriptedStatusError(GroqAPIStatusError):
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code
            Exception.__init__(self, f"status {status_code}")

    cases = [
        (ScriptedAuthError(), AuthenticationError),
        (ScriptedRateLimitError(), RateLimitError),
        (ScriptedStatusError(500), APIError),
        (type("M", (), {"content": None})(), InvalidResponseError),
    ]
    for exc, expected in cases:
        provider, _ = make_groq(exc)
        try:
            await provider.generate("Hi")
            print(f"FAIL: {type(exc).__name__} did not raise")
            return False
        except expected:
            continue
        except Exception as e:  # noqa: BLE001
            print(f"FAIL: {type(exc).__name__} raised {type(e).__name__}, "
                  f"expected {expected.__name__}")
            return False
    return True


def main() -> None:
    """Run all fallback-model checks and report the overall result."""
    print("=" * 60)
    print("Fallback Models Test (Gemini + Groq)")
    print("=" * 60)

    scenarios = [
        ("Tracked defaults are the verified ids",
         test_tracked_defaults_are_verified_models),
        ("Gemini constructs, passes model, parses",
         lambda: asyncio.run(test_gemini_constructs_and_passes_model())),
        ("Gemini error mapping unchanged",
         lambda: asyncio.run(test_gemini_error_mapping())),
        ("Groq constructs, passes model, parses",
         lambda: asyncio.run(test_groq_constructs_and_parses())),
        ("Groq error mapping unchanged",
         lambda: asyncio.run(test_groq_error_mapping())),
    ]

    passed = True
    for label, scenario in scenarios:
        print()
        print(label)
        try:
            result = scenario()
        except Exception as exc:  # noqa: BLE001 - report any crash as failure
            print(f"CRASHED: {type(exc).__name__}: {exc}")
            result = False
        print("PASSED" if result else "FAILED")
        passed = passed and result

    print()
    print("=" * 60)
    print(f"Fallback Models Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
