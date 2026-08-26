"""Regression tests for fallback LLM provider model configuration.

These tests detect *catalog drift* (retired / removed model IDs) without
requiring live provider access. They assert that the configured fallback
models are not known-retired identifiers and that no provider implementation
hardcodes a retired model ID.
"""

import pathlib

import pytest

from app.config.openrouter_models import OPENROUTER_MODELS
from app.core.config import settings

# Model IDs empirically found removed/retired from the live provider catalogs.
# If a provider returns 404/410/decommissioned for one of these, generation
# fails outright, which breaks CRAG query rewriting and chat.
KNOWN_RETIRED_MODELS = frozenset(
    {
        # Gemini
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-2.5-flash-lite",  # available only to newer accounts
        # Groq (decommissioned / removed)
        "llama-3.3-70b-versatile",
        "llama-3.3-70b-instruct",
        "llama-3.3-70b-specdec",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        # OpenRouter free pool (all removed from the catalog)
        "deepseek/deepseek-r1-0528:free",
        "qwen/qwen3-coder:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "mistralai/mistral-small-3.2-24b-instruct:free",
        "google/gemma-3-27b-it:free",
    }
)


def test_gemini_model_is_not_retired():
    assert settings.gemini_model, "gemini_model must be configured"
    assert settings.gemini_model not in KNOWN_RETIRED_MODELS


def test_groq_model_is_not_retired():
    assert settings.groq_model, "groq_model must be configured"
    assert settings.groq_model not in KNOWN_RETIRED_MODELS


def test_default_model_is_not_retired():
    assert settings.default_model, "default_model must be configured"
    assert settings.default_model not in KNOWN_RETIRED_MODELS


def test_openrouter_models_are_not_retired():
    assert OPENROUTER_MODELS, "OPENROUTER_MODELS must not be empty"
    for model in OPENROUTER_MODELS:
        assert model, "empty OpenRouter model id"
        assert model not in KNOWN_RETIRED_MODELS


def test_openrouter_models_use_free_slug():
    for model in OPENROUTER_MODELS:
        assert model.endswith(":free"), f"{model} is not a free-tier slug"


def test_configured_models_are_not_placeholders():
    for name in (
        settings.gemini_model,
        settings.groq_model,
        settings.default_model,
        *OPENROUTER_MODELS,
    ):
        assert name and "REPLACE" not in name, f"placeholder model id: {name!r}"


_PROVIDER_ROOT = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "llm"


def test_no_provider_hardcodes_retired_models():
    """Provider implementations must read the model from settings, never
    embed a retired literal."""
    scanned = [
        _PROVIDER_ROOT / "factory.py",
        _PROVIDER_ROOT / "provider_manager.py",
    ]
    scanned += list((_PROVIDER_ROOT / "providers").glob("*.py"))
    bad = []
    for path in scanned:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for retired in KNOWN_RETIRED_MODELS:
            if retired in text:
                bad.append((path.name, retired))
    assert not bad, f"retired model id hardcoded in provider code: {bad}"
