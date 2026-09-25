# Cold-Start Latency Audit (first `/chat` request)

## Scope
- Production endpoint: `https://docmind-ai-untx.onrender.com`
- First `/chat` request: ~10–12s cold, ~2s warm
- Production provider priority: `agnes,opencode,openrouter,gemini,groq` (from `.env.example`)
- Model pre-cached in image; `HF_HUB_OFFLINE=1` set; `ENABLE_EMBEDDINGS=true`
- No code changes intended — this is an informational audit.

## First-request initialization chain

1. `/chat` route (`routes/chat.py`) depends on:
   - `get_current_user` -> `get_auth_service` (`@lru_cache`) -> loads `users.json` / builds auth service (local I/O)
   - `get_chat_service` (`@lru_cache`) -> builds `ChatService` once
2. `get_chat_service` (`dependencies.py`) calls:
   - `get_embedding_service()` -> `EmbeddingService()` -> imports `sentence_transformers` + `torch` (inside `__init__`), loads `all-MiniLM-L6-v2`
   - `get_vector_store()` -> `FAISS` index load from `storage/faiss/index.faiss`
   - `get_bm25_retriever()` -> loads `documents.json`
   - `get_metadata_store()` -> loads `metadata.json`
   - `build_provider_manager()` (`factory.py`) -> constructs `ProviderManager`
3. `build_provider_manager()` calls provider builders in priority order until a usable provider is built. With `agnes` first and `AGNES_API_KEY`/model set:
   - `build_agnes_provider()` -> `build_agnes_pool()` -> `get_shared_catalog()` -> fetches `https://models.dev` JSON (~4.4MB) **if not already cached**
   - `OpenCode` pool also uses the shared catalog, so it reuses the cached fetch (no duplicate)
   - `build_openrouter_catalog()` -> may issue a separate OpenRouter `/models` HTTP call **if OpenRouter is reached as fallback** and OpenRouter API key present
   - `ProviderManager.__init__` itself does no network work
4. `ChatService` composition completes; query routing and retrieval run per request.

## Expensive operations on first request

| Operation | Location | Cost | Network? |
|---|---|---|---|
| `lru_cache` construction of `ChatService` / `EmbeddingService` / `ProviderManager` | `dependencies.py`, `embedding/service.py`, `factory.py` | Several seconds total | Yes (providers) |
| `sentence_transformers` + `torch` import + model load | `embedding/service.py` | ~1–3s | No (model pre-cached; `HF_HUB_OFFLINE=1`) |
| FAISS index load | `vector_store.py` | <1s (small) | No |
| `documents.json` / `metadata.json` load | `bm25_retriever.py`, `metadata_store.py` | <1s | No |
| `models.dev` catalog fetch (~4.4MB) | `models_dev_catalog.py` (shared) | ~2–5s | **Yes** |
| OpenRouter `/models` fetch (fallback only) | `openrouter_catalog.py` | ~1–3s | **Yes, only if reached** |

## Primary cold-start cause
The single biggest controllable contributor is the **first-request `lru_cache` build of `ProviderManager`**, which triggers the **`models.dev` catalog fetch** (~4.4MB) and potentially an **OpenRouter `/models` HTTP call** if OpenRouter is reached as a fallback on the first request. These are network-bound and happen per cold start.

Local I/O (FAISS, JSON stores) and lazy torch/sentence-transformers import are secondary contributors but are bounded and faster.

## What can safely move to startup (no behavior change)
- Build `EmbeddingService`, `VectorStore`, `BM25Retriever`, `MetadataStore`, `ProviderManager`, and `ChatService` once at startup and hold them in module-level singletons, so the first `/chat` request does not pay construction cost.
- Pre-fetch the `models.dev` shared catalog once at startup (cache it in the shared catalog cache) so the first request is not blocked by the 4.4MB download.
- Optionally pre-warm the OpenRouter catalog fetch only if OpenRouter is configured to be reached.

This does **not** change provider priority, the Agnes 10s attempt timeout, persistence, frontend, memory, or image handling.

## Smallest safe fix
Move `ChatService` (and its sub-services) construction out of the first `/chat` request into a startup-warm path:
1. In `main.py`, add a `lifespan` async context manager that calls `get_chat_service()` (and `get_auth_service()` if desired) once.
2. Ensure the shared `models.dev` catalog is fetched during `build_provider_manager()` at startup so it is cached before the first request.
3. Leave request-path dependencies as-is — they now hit already-warm singletons.

Expected effect: first `/chat` request drops from ~10–12s to roughly the warm time plus a fast local cache hit (~2–3s), because the only remaining network call (models.dev) is already cached at startup.
