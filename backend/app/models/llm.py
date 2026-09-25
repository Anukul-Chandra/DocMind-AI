"""DocMind compatibility response models over the gateway contracts."""

from gateway.llm_gateway.contracts import (
    LLMResponse as GatewayLLMResponse,
    LLMStreamChunk,
)


class LLMResponse(GatewayLLMResponse):
    """DocMind response adapter with chat and RAG provenance fields."""

    # Routing provenance (filled by ChatService, not by providers):
    # "general" | "document" | "metadata".
    category: str = "general"
    # Document chunks that contributed to the answer. Empty unless the
    # question was answered through the retrieval (RAG) path.
    sources: list[dict] = []


__all__ = ["LLMResponse", "LLMStreamChunk"]