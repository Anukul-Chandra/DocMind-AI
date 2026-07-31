from pydantic import BaseModel


class DocumentResponse(BaseModel):

    """
    Response returned after successfully processing a document.
    """

    filename: str
    chunk_count: int
    chunks: list[str]
