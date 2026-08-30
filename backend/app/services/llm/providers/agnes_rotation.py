"""Runtime rotation layer over the dynamically discovered Agnes free pool.

Each ``generate`` request selects exactly one model at a time from the healthy
(pool) — ``pool -> healthy candidates -> prefer previously-successful -> prefer
low latency -> deterministic tie-break -> ONE request`` — then on failure
cools down / marks dead the offending model and advances to the next candidate
until a model succeeds or the pool is exhausted.

Health rules mirror the OpenCode rotating layer:
- success -> healthy (recorded latency; preferred on future requests)
- HTTP 429 / 5xx / timeout / transport -> temporary cooldown
- model unavailable/invalid (404 or explicit unavailable) -> permanently dead
- authentication failure -> fatal, re-raised (a bad key fails identically on
  every model)

The configured fallback model (``settings.agnes_model``) is kept strictly
separate from the dynamic pool: it is only attempted after every dynamic
candidate has failed (or when no dynamic pool exists), and it is never claimed
to be dynamically discovered.
"""

import logging
import time
from collections.abc import Callable

import httpx

from app.services.llm.providers.agnes import (
    AGNES_DEFAULT_BASE_URL,
    request_completion,
)
from app.services.llm.providers.base import (
    AuthenticationError,
    BaseProvider,
    ProviderError,
)
from app.services.llm.providers.opencode_rotation import (
    COOLDOWN,
    DEAD,
    FATAL,
    ROTATE,
    CooldownTracker,
    classify_opencode_failure,
)

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_SECONDS = 30.0


class AgnesRotatingProvider(BaseProvider):
    """Runtime layer rotating across the discovered Agnes free-model pool.

    Pool candidates are ordered before each request by: previously successful
    first, then lowest recorded latency, then a stable deterministic tie-break
    (alphabetical) so ordering never depends on insertion order. A single
    request is made per candidate; failures cool down or permanently dead-lists
    the model and advance to the next candidate. If the dynamic pool is empty
    or every candidate fails, the configured fallback model is attempted once
    as a clearly-separate safety net.
    """

    def __init__(
        self,
        api_key: str,
        models: list[str],
        fallback_model: str,
        base_url: str = AGNES_DEFAULT_BASE_URL,
        timeout: int = 60,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the rotating provider.

        Args:
            api_key: The Agnes API key.
            models: The dynamic free-model pool, as a list of ids or a
                :class:`ModelPoolManager`. May be empty; the fallback model is
                then the only option.
            fallback_model: The configured fallback model id (e.g.
                ``settings.agnes_model``), kept separate from the pool.
            base_url: The Agnes OpenAI-compatible base URL.
            timeout: HTTP client timeout in seconds per attempt.
            cooldown_seconds: Temporary cooldown for rate-limited/unavailable
                models.
            clock: Injectable monotonic-style clock (test seam).
        """
        self._api_key = api_key
        self._pool_models = list(models)
        if not self._pool_models and not fallback_model:
            raise ValueError("AgnesRotatingProvider needs a pool or a fallback model")
        self._fallback_model = fallback_model
        self._base_url = base_url.rstrip("/")
        self._cooldown = CooldownTracker(
            default_seconds=cooldown_seconds, clock=clock
        )
        self._clock = clock
        self._dead_models: set[str] = set()
        #: model id -> last successful response latency (seconds)
        self._latency: dict[str, float] = {}
        #: model ids that have produced at least one successful response
        self._ever_successful: set[str] = set()
        self._last_successful_model: str | None = None
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
        )

    @property
    def model(self) -> str:
        """Return the model backing this provider.

        After a successful request this is the model that actually produced the
        last answer (correct provenance); before any success it is the model
        the next attempt would prefer.
        """
        if self._last_successful_model is not None:
            return self._last_successful_model
        if not self._pool_models:
            return self._fallback_model
        return self._pool_models[0]

    def cooldown_remaining(self, model_id: str) -> float:
        """Return remaining cooldown seconds for a model (introspection)."""
        return self._cooldown.remaining(model_id)

    def is_dead(self, model_id: str) -> bool:
        """Return True if a model was permanently marked unavailable."""
        return model_id in self._dead_models

    def _candidate_pool(self) -> list[str]:
        """Return the ordered list of candidate attempts for one request.

        Ordering: healthy (non-dead, non-cooling) pool models first, sorted by
        (previously successful, lowest latency, then alphabetical tie-break);
        the fallback model appended last as a clearly-separate safety net.
        """
        healthy = [
            model_id
            for model_id in self._pool_models
            if model_id not in self._dead_models
            and not self._cooldown.is_active(model_id)
        ]

        def _sort_key(model_id: str) -> tuple:
            return (
                0 if model_id in self._ever_successful else 1,
                self._latency.get(model_id, float("inf")),
                model_id,
            )

        return sorted(healthy, key=_sort_key)

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> str:
        """Generate a response, rotating through the pool then the fallback.

        Args:
            prompt: The user prompt to send to Agnes.
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.
            images: Optional list of base64-encoded image dicts.

        Returns:
            The generated text from the first successful model.

        Raises:
            ProviderError: If every candidate (pool and fallback) failed
                temporarily, or the request failed at the network level.
                Recoverable so ProviderManager can fail over to the next
                provider.
            AuthenticationError: If the endpoint rejects authentication.
        """
        candidates = self._candidate_pool()

        start = self._clock()
        for model_id in candidates:
            logger.debug("Agnes attempt: %s", model_id)
            try:
                text = await request_completion(
                    self._client,
                    model_id,
                    self._api_key,
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    images=images,
                )
            except (ProviderError, AuthenticationError) as exc:
                action = classify_opencode_failure(exc)
                if action == FATAL:
                    logger.warning("Agnes model %s failed fatally: %s", model_id, exc)
                    raise
                if action == DEAD:
                    self._dead_models.add(model_id)
                    logger.warning(
                        "Agnes model %s marked unavailable: %s", model_id, exc
                    )
                elif action == COOLDOWN:
                    self._cooldown.start(model_id)
                    logger.warning(
                        "Agnes model %s cooling down for %.0fs: %s",
                        model_id,
                        self.cooldown_remaining(model_id),
                        exc,
                    )
                else:  # ROTATE without penalty
                    logger.warning(
                        "Agnes model %s returned unusable output: %s", model_id, exc
                    )
                continue

            # Success: record health + latency so future requests prefer it.
            self._cooldown.clear(model_id)
            self._dead_models.discard(model_id)
            self._ever_successful.add(model_id)
            self._latency[model_id] = max(0.0, self._clock() - start)
            self._last_successful_model = model_id
            return text

        # Every dynamic candidate failed (or none existed). Try the separate
        # configured fallback once.
        if self._fallback_model and self._fallback_model not in candidates:
            logger.warning(
                "Agnes dynamic pool exhausted; trying configured fallback %s",
                self._fallback_model,
            )
            try:
                text = await request_completion(
                    self._client,
                    self._fallback_model,
                    self._api_key,
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    images=images,
                )
            except (ProviderError, AuthenticationError) as exc:
                action = classify_opencode_failure(exc)
                if action == FATAL:
                    raise
                logger.warning(
                    "Agnes fallback %s failed: %s", self._fallback_model, exc
                )
                raise ProviderError(
                    "All Agnes models and the fallback failed."
                ) from exc
            self._last_successful_model = self._fallback_model
            return text

        raise ProviderError(
            "All Agnes models are temporarily cooling down or permanently "
            "unavailable, and no fallback is configured."
        )
