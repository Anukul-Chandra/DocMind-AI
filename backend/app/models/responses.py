from pydantic import BaseModel


class ChunkResponse(BaseModel):
    id: int
    text: str


class DocumentResponse(BaseModel):

    """
    Response returned after successfully processing a document.
    """

    filename: str
    chunk_count: int
    chunks: list[ChunkResponse]
