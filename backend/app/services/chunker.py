from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings


def chunk_text(
    text: str,
    chunk_size: int = settings.chunk_size,
    chunk_overlap: int = settings.chunk_overlap,
) -> list[str]:
    """Split text into fixed-size character chunks with overlap.

    Args:
        text: The text to split into chunks.
        chunk_size: Maximum number of characters per chunk.
        chunk_overlap: Number of overlapping characters between consecutive chunks.

    Returns:
        A list of non-empty text chunks.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n",
            "\n",
            " ",
            "",
        ],
    )
    return [chunk for chunk in splitter.split_text(text) if chunk]
