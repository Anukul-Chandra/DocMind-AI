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
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


@dataclass(frozen=True)
class DocumentIndexResult:
    """Summary of a completed document indexing operation."""

    filename: str
    total_chunks: int
    total_embeddings: int


class DocumentIndexError(Exception):
    """Raised when a document cannot be fully indexed."""


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

    def index_document(
        self,
        pdf_path: str,
        workspace_id: str = DEFAULT_WORKSPACE,
    ) -> DocumentIndexResult:
        """Extract, clean, chunk, embed, and persist a PDF document.

        Args:
            pdf_path: Filesystem path to the PDF to index.
            workspace_id: The workspace the document belongs to.

        Returns:
            A summary of the indexed document.

        Raises:
            DocumentIndexError: If the document cannot be extracted or indexed.
        """
        try:
            text = extract_text_from_pdf(self._to_upload_file(pdf_path))
            cleaned_text = clean_text(text)
            chunks = chunk_text(cleaned_text)

            embeddings = self._embedding_service.generate_embeddings(chunks)
            self._vector_store.add_embeddings(embeddings)
            self._metadata_store.add_documents(
                chunks,
                Path(pdf_path).name,
                workspace_id,
            )

            self._vector_store.save(settings.faiss_index_path)
            self._metadata_store.save(settings.metadata_path)
        except Exception as exc:
            raise DocumentIndexError(
                f"Failed to index document {Path(pdf_path).name}: {exc}"
            ) from exc

        return DocumentIndexResult(
            filename=Path(pdf_path).name,
            total_chunks=len(chunks),
            total_embeddings=len(embeddings),
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