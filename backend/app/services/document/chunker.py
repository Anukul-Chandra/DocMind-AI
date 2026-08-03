"""Text chunking for the document indexing pipeline."""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings


class Chunker:
    """Split document text into fixed-size chunks with overlap."""

    def __init__(
        self,
        chunk_size: int = settings.chunk_size,
        chunk_overlap: int = settings.chunk_overlap,
    ) -> None:
        """Initialize the chunker with its sizing configuration.

        Args:
            chunk_size: Maximum number of characters per chunk.
            chunk_overlap: Number of overlapping characters between chunks.
        """
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )

    def chunk(self, text: str) -> list[str]:
        """Split the text into non-empty chunks.

        Args:
            text: The text to split.

        Returns:
            A list of non-empty text chunks.
        """
        return [chunk for chunk in self._splitter.split_text(text) if chunk]
