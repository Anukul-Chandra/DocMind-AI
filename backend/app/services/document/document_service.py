"""Document indexing orchestration for DocMind AI."""

from dataclasses import dataclass
from pathlib import Path

from app.services.document.chunker import Chunker
from app.services.document.pdf_processor import PDFProcessor
from app.services.embedding import EmbeddingService
from app.services.text_cleaner import clean_text
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


class DocumentIndexError(Exception):
    """Raised when a document cannot be fully indexed."""


@dataclass(frozen=True)
class IndexDocumentResult:
    """Summary of a completed document indexing operation.

    Attributes:
        filename: The name of the indexed document.
        total_chunks: The number of chunks produced and indexed.
        total_embeddings: The number of embeddings generated for the chunks.
        status: The outcome of the indexing operation.
    """

    filename: str
    total_chunks: int
    total_embeddings: int
    status: str


class DocumentService:
    """Orchestrate the full document indexing pipeline.

    This service composes PDF text extraction, text cleaning, chunking,
    embedding generation, FAISS storage, and metadata persistence. It depends
    only on the collaborators it receives and is responsible solely for
    orchestration.
    """

    def __init__(
        self,
        pdf_processor: PDFProcessor,
        chunker: Chunker,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        metadata_store: MetadataStore,
        faiss_index_path: str | None = None,
        metadata_path: str | None = None,
    ) -> None:
        """Initialize the document service with its collaborators.

        Args:
            pdf_processor: Extracts text from a PDF file.
            chunker: Splits cleaned text into chunks.
            embedding_service: Generates embeddings for the chunks.
            vector_store: Stores the embeddings in a FAISS index.
            metadata_store: Stores the chunk metadata.
            faiss_index_path: Optional path to persist the FAISS index to.
            metadata_path: Optional path to persist the chunk metadata to.
        """
        self._pdf_processor = pdf_processor
        self._chunker = chunker
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        self._metadata_store = metadata_store
        self._faiss_index_path = faiss_index_path
        self._metadata_path = metadata_path

    async def index_document(
        self,
        file_path: str,
        workspace_id: str = DEFAULT_WORKSPACE,
        document_id: str | None = None,
        owner_id: str = "",
        filename: str | None = None,
    ) -> IndexDocumentResult:
        """Index an uploaded document end to end.

        Args:
            file_path: Filesystem path to the PDF to index.
            workspace_id: The workspace the document belongs to.
            document_id: The identifier of the owning document, or None.
            owner_id: The user id that owns the document chunks. Empty for
                legacy indexes created before ownership was tracked.
            filename: Optional display filename recorded in the metadata. When
                omitted, the base name of ``file_path`` is used. Callers that
                store uploads under server-generated names pass the original
                client filename here so it is preserved for display.

        Returns:
            A summary with the filename, chunk count, embedding count, and status.

        Raises:
            DocumentIndexError: If the document cannot be extracted or indexed.
        """
        display_filename = filename or Path(file_path).name
        try:
            text = self._pdf_processor.extract_text(file_path)
            cleaned_text = clean_text(text)
            chunks = self._chunker.chunk(cleaned_text)

            embeddings = self._embedding_service.generate_embeddings(chunks)
            self._vector_store.add_embeddings(embeddings)
            self._metadata_store.add_documents(
                chunks,
                display_filename,
                workspace_id,
                document_id,
                owner_id,
            )

            if self._faiss_index_path is not None:
                self._vector_store.save(self._faiss_index_path)
            if self._metadata_path is not None:
                self._metadata_store.save(self._metadata_path)
        except Exception as exc:
            raise DocumentIndexError(
                f"Failed to index document {display_filename}: {exc}"
            ) from exc

        return IndexDocumentResult(
            filename=display_filename,
            total_chunks=len(chunks),
            total_embeddings=len(embeddings),
            status="indexed",
        )
