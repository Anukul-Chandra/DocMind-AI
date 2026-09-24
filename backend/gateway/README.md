# llm-gateway

Reusable LLM gateway — provider contracts, failover, model pool/curation, cooldown, failure classification, catalog discovery, and OpenAI-compatible providers. Extracted from DocMind AI (`backend/gateway/llm_gateway`) to be usable by any Python project without importing `app`.

## Scope

**Reusable (gateway-owned):**
- `contracts` — `BaseProvider`, `ProviderError` hierarchy (`APIError`, `AuthenticationError`, `RateLimitError`, `InvalidResponseError`, `ModelCatalogError`, `NoFreeModelsError`, `LLMUnavailableError`, `RecoverableError`), `LLMResponse`/`LLMStreamChunk`, `build_user_content`
- `ProviderManager` — failover across providers, image-error retry, streaming failover before first chunk
- `ModelPoolManager` + `curate_models`/`build_curated_pool` — general-purpose model filtering and preferred-order pool
- `CooldownTracker` — per-model temporary cooldown with injectable clock
- `failure_policy.classify_failure` — `COOLDOWN`/`DEAD`/`ROTATE`/`FATAL` classification used by rotating providers
- `catalog.ModelsDevCatalog` — authoritative `https://models.dev/api.json` discovery (TTL 6h, stale-while-revalidate, thread-safe, `parse_provider_free_models`/`get_shared_catalog`)
- `providers.AgnesProvider` / `providers.OpenCodeProvider` — single-model OpenAI-compatible `httpx` providers (no DocMind imports). Rotating wrappers remain in DocMind.

**DocMind-specific (intentionally not in gateway):**
- `OpenRouter` (custom `attempt_timeout`/`total_timeout`/deadline, `dead_models`, SSE streaming via `client.stream`), `Gemini` (`google-genai` SDK), `Groq` (`groq` SDK), OpenRouter catalog (`openai` SDK), Agnes/OpenCode rotating wrappers `app.services.llm.providers.*_rotation`, `factory`/`provider_priority`/`ChatService`/`RAG`.

## Install

```bash
pip install -e backend/gateway        # from DocMind repo
# or copy backend/gateway as standalone package `llm-gateway`
pip install llm-gateway               # once published
```
Runtime deps: `pydantic`, `httpx` only (see `backend/gateway/pyproject.toml`). No `fastapi`, `torch`, `openai`, `google-genai`, `groq`, `sqlalchemy`, `faiss`.

## Basic ProviderManager usage

```python
from gateway.llm_gateway import ProviderManager, LLMResponse
from gateway.llm_gateway.providers.agnes import AgnesProvider
from gateway.llm_gateway.providers.opencode import OpenCodeProvider
from gateway.llm_gateway.model_pool import ModelPoolManager

# any BaseProvider works — inject via constructor, no global settings
p1 = OpenCodeProvider(model="mimo-v2-flash")
p2 = AgnesProvider(api_key="...", model="agnes-2.5-flash")
manager = ProviderManager([p1, p2])

resp: LLMResponse = await manager.generate("hello", system_prompt="be concise")
print(resp.text, resp.provider, resp.model)

# failover: next provider is tried on RecoverableError
# streaming (failover before first chunk)
async for chunk in manager.generate_stream("hello"):
    print(chunk.content, end="")
```

## Agnes / OpenCode providers

```python
from gateway.llm_gateway.providers.agnes import AgnesProvider
from gateway.llm_gateway.providers.opencode import OpenCodeProvider

agnes = AgnesProvider(api_key="...", model="agnes-2.5-flash", base_url="https://apihub.agnes-ai.com/v1", timeout=60, attempt_timeout=10.0)
opencode = OpenCodeProvider(model="mimo-v2-flash", timeout=60)

# multimodal (images as OpenAI image_url parts)
await agnes.generate("describe", images=[{"mime": "image/png", "data": "<base64>"}])
```

Both share `build_user_content` and raise gateway errors (`AuthenticationError`, `RateLimitError`, `APIError`, `InvalidResponseError`, `ProviderError`) for `failure_policy`/`ProviderManager` handling. See `gateway.llm_gateway.providers` re-exports.

## ModelsDevCatalog usage

```python
from gateway.llm_gateway.catalog import ModelsDevCatalog, get_shared_catalog, parse_provider_free_models
from gateway.llm_gateway.model_pool import curate_models, build_curated_pool

# shared process-wide TTL cache (6h)
catalog = get_shared_catalog()
agnes_free = catalog.get_free_models("agnes")          # ["agnes-2.5-flash", ...]
opencode_free = catalog.get_free_models("opencode")   # pricing cost==0

# test injection
catalog = ModelsDevCatalog(client=lambda: httpx.Client(timeout=10), ttl_seconds=60, clock=time.monotonic)

# curation / pool
curated = curate_models(agnes_free)
pool = build_curated_pool(agnes_free, preferred=["agnes-2.5-flash"])
```

`parse_provider_free_models(data, provider)` is pure and degrades malformed payloads to `[]` (`cost.input==0 and cost.output==0`).

## Notes

- DocMind compatibility shims remain: `app.services.llm.providers.agnes`, `opencode`, `model_pool`, `models_dev_catalog`, etc. re-export gateway.
- `factory` (`app.services.llm.factory`) still builds `ProviderManager` with DocMind `provider_priority` and static fallbacks (`OPENROUTER_MODELS`); not moved to gateway.
