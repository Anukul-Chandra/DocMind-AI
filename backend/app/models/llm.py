from pydantic import BaseModel


class LLMResponse(BaseModel):
    """Response returned by an LLM provider."""

    text: str
    provider: str
    model: str = ""


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
