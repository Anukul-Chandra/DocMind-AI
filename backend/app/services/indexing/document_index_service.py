"""Service for indexing PDF documents from a filesystem path."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.services.chunker import chunk_text
from app.services.embedding import EmbeddingService
from app.services.pdf import extract_text_from_pdf
from app.services.text_cleaner import clean_text
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore


@dataclass(frozen=True)
class DocumentIndexResult:
    """Summary of a completed document indexing operation."""

    filename: str
    chunks_indexed: int
    embedding_count: int


class DocumentIndexService:
    """Index an uploaded PDF so it becomes searchable.

    This service composes the full indexing pipeline: PDF text extraction,
    text cleaning, chunking, embedding generation, storage in FAISS, and
    persistence of both the FAISS index and chunk metadata to disk.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        metadata_store: MetadataStore,
    ) -> None:
        """Initialize the document indexing service with its collaborators.

        Args:
            embedding_service: Generates embeddings for text chunks.
            vector_store: Stores embeddings in a FAISS index.
            metadata_store: Stores chunk metadata in JSON form.
        """
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        self._metadata_store = metadata_store

    def index_document(self, pdf_path: str) -> DocumentIndexResult:
        """Extract, clean, chunk, embed, and persist a PDF document.

        Args:
            pdf_path: Filesystem path to the PDF to index.

        Returns:
            A summary of the indexed document.

        Raises:
            HTTPException: If the PDF cannot be parsed or contains no text.
            Exception: If indexing fails and the PDF is invalid.
        """
        text = extract_text_from_pdf(self._to_upload_file(pdf_path))
        cleaned_text = clean_text(text)
        chunks = chunk_text(cleaned_text)

        embeddings = self._embedding_service.generate_embeddings(chunks)
        self._vector_store.add_embeddings(embeddings)
        self._metadata_store.add_documents(chunks, Path(pdf_path).name)

        self._vector_store.save(settings.faiss_index_path)
        self._metadata_store.save(settings.metadata_path)

        return DocumentIndexResult(
            filename=Path(pdf_path).name,
            chunks_indexed=len(chunks),
            embedding_count=len(embeddings),
        )

    @staticmethod
    def _to_upload_file(pdf_path: str) -> UploadFile:
        """Wrap the PDF at the given path as an UploadFile for the extractor.

        Args:
            pdf_path: Absolute path to the PDF to wrap.

        Returns:
            An UploadFile backed by the PDF's bytes.
        """
        with open(pdf_path, "rb") as f:
            data = f.read()
        return UploadFile(
            file=BytesIO(data),
            filename=Path(pdf_path).name,
            headers={"content-type": "application/pdf"},
        )