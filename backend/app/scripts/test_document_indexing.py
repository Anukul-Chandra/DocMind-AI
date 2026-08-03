"""Manual integration test for the DocumentService.

This manually indexes a single PDF end to end and prints a summary, then
reloads the persisted FAISS index and metadata from disk to verify that the
indexed content was stored correctly.

Usage:
    python -m app.scripts.test_document_indexing <pdf_path>

It is intended to be run manually only. It does not create any API endpoint.
"""

import asyncio
import os
import sys

from app.core.config import settings
from app.services.document import Chunker, DocumentService, PDFProcessor
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore


def build_document_service() -> tuple[DocumentService, VectorStore, MetadataStore]:
    """Build a DocumentService with its collaborators.

    Returns:
        A tuple of the DocumentService, its VectorStore, and its MetadataStore.
    """
    embedding_service = EmbeddingService()
    vector_store = VectorStore(dimension=embedding_service.get_embedding_dimension())
    metadata_store = MetadataStore()
    service = DocumentService(
        PDFProcessor(),
        Chunker(),
        embedding_service,
        vector_store,
        metadata_store,
        faiss_index_path=settings.faiss_index_path,
        metadata_path=settings.metadata_path,
    )
    return service, vector_store, metadata_store


def main(pdf_path: str) -> None:
    """Run the document indexing integration test.

    Args:
        pdf_path: Path to the PDF file to index.
    """
    print("=" * 60)
    print("Document Indexing Test")
    print("=" * 60)

    if not pdf_path.lower().endswith(".pdf"):
        print("\nError: the file must have a .pdf extension.")
        print("=" * 60)
        return

    if not os.path.exists(pdf_path):
        print(f"\nPDF not found: {pdf_path}")
        print("=" * 60)
        return

    service, vector_store, metadata_store = build_document_service()

    try:
        result = asyncio.run(service.index_document(pdf_path))
    except Exception as exc:  # noqa: BLE001 - manual test should not crash
        print("\nIndexing failed:")
        print(f"  {type(exc).__name__}: {exc}")
        print("=" * 60)
        return

    print()
    print("Filename:")
    print(result.filename)
    print()
    print("Chunks Indexed:")
    print(result.total_chunks)
    print()
    print("Embeddings Generated:")
    print(result.total_embeddings)
    print()

    # Verify the persisted on-disk assets by reloading them.
    reloaded_store = VectorStore.load(settings.faiss_index_path, vector_store._index.d)
    faiss_total = reloaded_store._index.ntotal

    reloaded_metadata = MetadataStore()
    reloaded_metadata.load(settings.metadata_path)
    metadata_total = len(reloaded_metadata.get_all_documents())

    print("FAISS Total Vectors:")
    print(faiss_total)
    print()
    print("Metadata Records:")
    print(metadata_total)
    print()

    print("Verification:")
    print(f"  MetadataStore.get_all_documents() = {len(metadata_store.get_all_documents())} records")
    print(f"  VectorStore.load(...)._index.ntotal = {faiss_total} vectors")
    print()
    print("Indexing completed successfully.")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("python -m app.scripts.test_document_indexing <pdf_path>")
        sys.exit(1)
    main(sys.argv[1])
