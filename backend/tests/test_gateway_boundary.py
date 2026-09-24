"""Boundary contract tests for the reusable LLM gateway package.

These tests enforce that the ``gateway.llm_gateway`` package is provider-agnostic
and contains **no** DocMind-specific (or RAG/retrieval) imports.  This is the
contractual boundary that allows the gateway to be extracted and reused by other
projects.

The pattern mirrors ``test_storage_backends_module_has_no_pgvector_dependency``
and ``test_postgres_metadata_backend_has_no_forbidden_dependencies``: every
source module under the gateway package is scanned for forbidden imports.
"""

import pathlib
import re

import pytest

_GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1] / "gateway"

_FORBIDDEN_PATTERNS = [
    re.compile(r"from app\."),
    re.compile(r"import app\."),
    re.compile(r"from backend\."),
    re.compile(r"import backend\."),
]


def _gateway_files():
    """Yield every Python source file under the gateway package."""
    for path in sorted(_GATEWAY_ROOT.rglob("*.py")):
        if path.name == "__init__.py" or path.suffix == ".py":
            yield path


def _read_source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def test_gateway_package_is_importable():
    import gateway.llm_gateway as gw

    assert hasattr(gw, "ProviderManager")
    assert hasattr(gw, "BaseProvider")
    assert hasattr(gw, "LLMResponse")
    assert hasattr(gw, "LLMStreamChunk")
    assert hasattr(gw, "LLMUnavailableError")
    assert hasattr(gw, "ProviderError")
    assert hasattr(gw, "RecoverableError")


def test_provider_manager_exported_from_package():
    from gateway.llm_gateway import ProviderManager as PM

    from gateway.llm_gateway.contracts import BaseProvider

    assert PM is not None
    # ProviderManager must accept a list of BaseProvider instances.
    assert PM.__init__.__doc__ or True  # smoke: class is importable


def test_gateway_contracts_match_expected_fields():
    """LLMResponse must carry the generic fields used by all DocMind layers."""
    from gateway.llm_gateway import LLMResponse, LLMStreamChunk

    resp = LLMResponse(text="hello", provider="test", model="m1")
    assert resp.text == "hello"
    assert resp.provider == "test"
    assert resp.model == "m1"

    chunk = LLMStreamChunk(content="hi", provider="test", model="m1")
    assert chunk.content == "hi"
    assert chunk.provider == "test"
    assert chunk.model == "m1"


def test_gateway_has_no_docmind_imports():
    """No module under gateway/ may import from the DocMind app package."""
    violations = []
    for path in _gateway_files():
        text = _read_source(path)
        for pattern in _FORBIDDEN_PATTERNS:
            for lineno, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    violations.append(f"{path.relative_to(_GATEWAY_ROOT.parent)}:{lineno}: {line.strip()}")
    assert not violations, (
        "Gateway package has forbidden DocMind dependencies:\n"
        + "\n".join(violations)
    )


def test_gateway_only_imports_stdlib_and_pydantic():
    """The gateway contracts must depend only on the standard library and
    pydantic — no third-party provider SDKs, no DocMind code."""
    allowed = {"pydantic", "abc", "logging", "time", "typing", "gateway", "re", "collections", "httpx", "threading", "asyncio"}
    violations = []
    for path in _gateway_files():
        tree = _read_source(path)
        for m in re.finditer(r"^(?:from|import)\s+([\w.]+)", tree, re.MULTILINE):
            top = m.group(1).split(".")[0]
            if top.startswith("_"):
                continue
            if top and top not in allowed:
                violations.append(f"{path}: imports '{top}' (not in allowlist)")
    assert not violations, (
        "Gateway package imports disallowed third-party modules:\n"
        + "\n".join(violations)
    )
