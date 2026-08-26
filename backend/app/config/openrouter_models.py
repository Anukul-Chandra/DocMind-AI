"""Trusted free OpenRouter models used as the default model pool.

All entries were verified against the live OpenRouter catalog
(``GET /api/v1/models``) on the fix date. The previous set
(deepseek-r1-0528:free, qwen3-coder:free, llama-3.3-70b-instruct:free,
mistral-small-3.2-24b-instruct:free, gemma-3-27b-it:free) had all been
removed from the catalog. Three entries below were additionally smoke-tested
with a chat completion and returned non-empty content; the remaining two were
confirmed present in the catalog but were rate-limited (HTTP 429) at test time.
"""

OPENROUTER_MODELS: list[str] = [
    "poolside/laguna-s-2.1:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "minimax/minimax-m3:free",
]
