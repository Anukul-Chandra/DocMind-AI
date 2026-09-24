"""Compatibility adapter for the extracted gateway OpenCode provider."""

from gateway.llm_gateway.providers.opencode import (
    OPENCODE_BASE_URL,
    OpenCodeProvider,
    request_completion,
)

__all__ = ["OPENCODE_BASE_URL", "request_completion", "OpenCodeProvider"]
