"""Per-model cooldown tracking for the reusable LLM gateway boundary."""

import time
from collections.abc import Callable


#: Default temporary-cooldown duration applied to rate-limited/unavailable
#: models. Small by design: cooldowns only need to outlive a single request's
#: retry burst, not punish the model.
DEFAULT_COOLDOWN_SECONDS = 30.0


class CooldownTracker:
    """Track temporary per-model cooldown windows on an injectable clock.

    Uses monotonic time so wall-clock changes cannot shorten cooldowns. The
    clock is injectable so tests can advance time deterministically without
    sleeping.
    """

    def __init__(
        self,
        default_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the tracker.

        Args:
            default_seconds: Cooldown window applied when none is given.
            clock: Zero-argument callable returning the current time in
                seconds (monotonic by default).
        """
        self._default_seconds = max(0.0, default_seconds)
        self._clock = clock
        self._until: dict[str, float] = {}

    def start(self, model_id: str) -> None:
        """Put a model into temporary cooldown starting now."""
        self._until[model_id] = self._clock() + self._default_seconds

    def is_active(self, model_id: str) -> bool:
        """Return True while a model is still cooling down."""
        until = self._until.get(model_id)
        return until is not None and self._clock() < until

    def remaining(self, model_id: str) -> float:
        """Return the remaining cooldown seconds for a model (0 if none)."""
        until = self._until.get(model_id)
        if until is None:
            return 0.0
        return max(0.0, until - self._clock())

    def clear(self, model_id: str) -> None:
        """Reset any recorded temporary failure state for a model."""
        self._until.pop(model_id, None)