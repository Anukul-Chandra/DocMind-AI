"""Compatibility adapter for the extracted gateway CooldownTracker."""

from gateway.llm_gateway.cooldown import (
    CooldownTracker,
    DEFAULT_COOLDOWN_SECONDS,
)

__all__ = [
    "CooldownTracker",
    "DEFAULT_COOLDOWN_SECONDS",
]