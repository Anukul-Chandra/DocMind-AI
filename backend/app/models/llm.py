from pydantic import BaseModel


class LLMResponse(BaseModel):
    """Response returned by an LLM provider."""

    text: str
    provider: str
    model: str = ""
    # Routing provenance (filled by ChatService, not by providers):
    # "general" | "document" | "metadata".
    category: str = "general"
    # Document chunks that contributed to the answer. Empty unless the
    # question was answered through the retrieval (RAG) path.
    sources: list[dict] = []


class LLMStreamChunk(BaseModel):
    """A single chunk of streamed LLM output.

    Attributes:
        content: The text fragment produced by the provider.
        provider: The provider that produced the fragment.
        model: The model that produced the fragment.
    """

    content: str
    provider: str
    model: str = ""
