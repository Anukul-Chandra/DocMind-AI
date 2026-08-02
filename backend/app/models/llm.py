from pydantic import BaseModel


class LLMResponse(BaseModel):
    """Response returned by an LLM provider."""

    text: str
    provider: str
    model: str = ""
