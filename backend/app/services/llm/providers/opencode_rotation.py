import logging
import time
from collections.abc import Callable

import httpx

from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.providers.base import (
    BaseProvider,
    ProviderError,
)
from app.services.llm.providers.cooldown import (
    CooldownTracker,
    DEFAULT_COOLDOWN_SECONDS,
)
from app.services.llm.providers.opencode import OPENCODE_BASE_URL, request_completion
from gateway.llm_gateway.failure_policy import (
    COOLDOWN,
    DEAD,
    FATAL,
    ROTATE,
    _MODEL_UNAVAILABLE_MARKERS,
    _MODEL_UNAVAILABLE_PATTERN,
    classify_failure as classify_opencode_failure,
)

# Backwards compatibility: original classify_failure alias was opencode-named.
classify_failure = classify_opencode_failure

logger = logging.getLogger(__name__)


class OpenCodeRotatingProvider(BaseProvider):
    """Runtime layer rotating across the discovered OpenCode model pool.

    Wraps the existing :class:`ModelPoolManager` (no separate pool system):
    each request attempts models in pool order, applying the runtime failure
    rules from ``classify_opencode_failure``:

    - temporary failures put the model into a short configurable cooldown
      and rotate to the next model
    - permanently unavailable models (404 / explicit model-unavailable) are
      skipped for the remainder of the provider lifetime
    - successes reset that model's temporary state and return immediately
    - if every eligible model is cooling down or dead, a clean recoverable
      :class:`ProviderError` is raised (never a tight loop, never a hang)

    No startup health checks are performed and nothing about the dynamic
    catalog is hardcoded; cooldown expiry alone makes models eligible again.
    """

    def __init__(
        self,
        pool: ModelPoolManager | list[str],
        timeout: int = 60,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        base_url: str = OPENCODE_BASE_URL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the rotating provider.

        Args:
            pool: A :class:`ModelPoolManager`, or a list of discovered
                OpenCode model ids to wrap in one.
            timeout: HTTP client timeout in seconds per attempt.
            cooldown_seconds: Temporary cooldown applied to rate-limited or
                temporarily-unavailable models.
            base_url: The OpenAI-compatible OpenCode inference base URL.
            clock: Injectable monotonic-style clock (test seam).
        """
        if isinstance(pool, ModelPoolManager):
            self._pool = pool
        else:
            self._pool = ModelPoolManager(list(pool))
        self._cooldown = CooldownTracker(
            default_seconds=cooldown_seconds, clock=clock
        )
        self._clock = clock
        self._dead_models: set[str] = set()
        #: Model id that produced the most recent successful answer, so the
        #: ``model`` property reports real provenance even after the pool
        #: cursor is rewound for the next request.
        self._last_successful_model: str | None = None
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
        )

    @property
    def model(self) -> str:
        """Return the model backing this provider.

        After a successful request this is the model that actually produced
        the last answer (correct provenance); before any success it is the
        model the next attempt would use.

        Returns:
            The model identifier.
        """
        if self._last_successful_model is not None:
            return self._last_successful_model
        return self._pool.get_current_model()

    def cooldown_remaining(self, model_id: str) -> float:
        """Return remaining cooldown seconds for a model (introspection)."""
        return self._cooldown.remaining(model_id)

    def is_dead(self, model_id: str) -> bool:
        """Return True if a model was permanently marked unavailable."""
        return model_id in self._dead_models

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> str:
        """Generate a response, rotating through eligible pool models.

        Args:
            prompt: The user prompt to send to OpenCode.
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text from the first successful model.

        Raises:
            ProviderError: If every eligible model failed temporarily
                (cooldown/dead) within one pass, or the request failed at
                the network level. Recoverable so a future ProviderManager
                integration can fail over to the next provider.
            AuthenticationError: If the endpoint rejects authentication.
            APIError: If a non-recoverable HTTP error occurs (e.g. a plain
                HTTP 400).
        """
        total = self._pool.total_models()
        attempts = 0
        while attempts < total:
            model_id = self._next_eligible_model()
            if model_id is None:
                break
            attempts += 1
            logger.debug("OpenCode attempt %d/%d: %s", attempts, total, model_id)
            try:
                text = await request_completion(
                    self._client,
                    model_id,
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    images=images,
                )
            except ProviderError as exc:
                action = classify_opencode_failure(exc)
                if action == FATAL:
                    logger.warning("OpenCode model %s failed fatally: %s", model_id, exc)
                    raise
                if action == DEAD:
                    self._dead_models.add(model_id)
                    logger.warning(
                        "OpenCode model %s marked unavailable: %s", model_id, exc
                    )
                elif action == COOLDOWN:
                    self._cooldown.start(model_id)
                    logger.warning(
                        "OpenCode model %s cooling down for %.0fs: %s",
                        model_id,
                        self.cooldown_remaining(model_id),
                        exc,
                    )
                else:  # ROTATE without penalty
                    logger.warning(
                        "OpenCode model %s returned unusable output: %s",
                        model_id,
                        exc,
                    )
                self._advance_past(model_id)
                continue

            # Success: reset any temporary failure state for this model.
            self._cooldown.clear(model_id)
            self._last_successful_model = model_id
            # Rewind to the pool head so later requests re-scan from the
            # first eligible model; expired-cooldown models become reachable
            # again naturally.
            self._pool.reset()
            return text

        self._pool.reset()
        raise ProviderError(
            "All OpenCode models are temporarily cooling down or "
            "permanently unavailable."
        )

    def _advance_past(self, model_id: str) -> None:
        """Move the pool cursor off a just-failed model (best effort)."""
        if self._pool.get_current_model() == model_id:
            try:
                self._pool.move_next()
            except RuntimeError:
                pass

    def _next_eligible_model(self) -> str | None:
        """Return the next non-dead, non-cooling model, or None.

        Scans forward through the existing ModelPoolManager without ever
        blocking on a cooldown window.
        """
        seen = 0
        while seen < self._pool.total_models():
            model_id = self._pool.get_current_model()
            if (
                model_id not in self._dead_models
                and not self._cooldown.is_active(model_id)
            ):
                return model_id
            seen += 1
            try:
                self._pool.move_next()
            except RuntimeError:
                break
        return None
