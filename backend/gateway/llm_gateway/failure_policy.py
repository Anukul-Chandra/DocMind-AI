"""Reusable failure classification / rotation policy for the LLM gateway boundary.

This module owns the shared classification that was previously embedded in the
OpenCode rotating layer and imported directly by the Agnes rotation layer
(``Agnes → OpenCode`` coupling).  The logic is provider-agnostic: it maps the
gateway contract errors onto the four rotation actions that both rotating
providers consume.

Behavior is preserved exactly from the original
``app.services.llm.providers.opencode_rotation.classify_opencode_failure``.
"""

import re

from gateway.llm_gateway.contracts import (
    APIError,
    AuthenticationError,
    InvalidResponseError,
    ProviderError,
    RateLimitError,
)

#: Substrings that, inside an HTTP 400 body, explicitly indicate the model
#: itself is unavailable/invalid (rather than a generic bad request). Only
#: these turn a 400 into a permanent dead-model classification.
_MODEL_UNAVAILABLE_MARKERS: frozenset[str] = frozenset(
    {
        "model unavailable",
        "unavailable model",
        "invalid model",
        "unknown model",
        "model not found",
    }
)

#: Matches availability phrases with filler words that real provider bodies
#: insert between "model" and the failure word, e.g.
#: ``"Upstream request failed: Model is unavailable."``. Without this, such a
#: 400 would be misread as a fatal bad request instead of a dead model.
_MODEL_UNAVAILABLE_PATTERN = re.compile(
    r"\bmodel\s+(?:is|was|currently|became)?\s*(?:unavailable|not found)\b"
)

# Failure actions produced by classify_failure / classify_opencode_failure.
COOLDOWN = "cooldown"  # temporary: skip for now, eligible again later
DEAD = "dead"  # permanent for the pool lifecycle: never attempted again
ROTATE = "rotate"  # try the next model without penalizing this one
FATAL = "fatal"  # re-raise immediately; do not rotate


def classify_failure(exc: Exception) -> str:
    """Classify a provider attempt failure into a runtime action.

    Rules (preserved verbatim from the original OpenCode policy):
    - HTTP 429 (rate limit): temporary cooldown, never permanent.
    - HTTP 5xx / unspecified-status API errors (temporary upstream failure):
      temporary cooldown.
    - Timeouts and transport failures: temporary cooldown.
    - HTTP 404 or an HTTP 400 whose body clearly says the model itself is
      unavailable/invalid: permanently dead for this pool lifecycle.
    - Any other HTTP 400: fatal — re-raised without rotating, preserving the
      provider error behavior (a malformed request fails identically on
      every model).
    - Malformed/empty responses: rotate to the next model without penalty.
    - Authentication failures: fatal.

    Args:
        exc: The provider error raised by a single model attempt.

    Returns:
        One of :data:`COOLDOWN`, :data:`DEAD`, :data:`ROTATE`, or
        :data:`FATAL`.
    """
    if isinstance(exc, AuthenticationError):
        return FATAL
    if isinstance(exc, RateLimitError):
        return COOLDOWN
    if isinstance(exc, InvalidResponseError):
        return ROTATE
    if isinstance(exc, APIError):
        status_code = exc.status_code
        if status_code == 404:
            return DEAD
        if status_code is None or status_code >= 500 or status_code == 408:
            return COOLDOWN
        if status_code == 400:
            detail = str(exc).lower()
            if any(marker in detail for marker in _MODEL_UNAVAILABLE_MARKERS):
                return DEAD
            if _MODEL_UNAVAILABLE_PATTERN.search(detail):
                return DEAD
            return FATAL
        return FATAL
    # ProviderError covers timeouts ("timed out") and transport failures;
    # both are treated as temporary model-side conditions.
    return COOLDOWN


# Backwards-compatibility alias: the original name used by rotation layers
# and tests. Kept so ``from gateway.llm_gateway.failure_policy import
# classify_opencode_failure`` and legacy opencode_rotation re-exports continue
# to work.
classify_opencode_failure = classify_failure

__all__ = [
    "COOLDOWN",
    "DEAD",
    "FATAL",
    "ROTATE",
    "_MODEL_UNAVAILABLE_MARKERS",
    "_MODEL_UNAVAILABLE_PATTERN",
    "classify_failure",
    "classify_opencode_failure",
]
