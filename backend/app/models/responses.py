from pydantic import BaseModel


class DocumentResponse(BaseModel):
    """Response model for the document upload endpoint."""

    filename: str
    chunk_count: int
    chunks: list[str]
