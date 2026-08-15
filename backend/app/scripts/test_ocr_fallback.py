"""Focused regression verification of the OCR fallback for scanned PDFs.

Previously, PDFs without a selectable text layer were rejected during
extraction, so image-only (scanned) documents could not be indexed. This script
proves the fix:

    1. A PDF with selectable text keeps the existing extraction path and never
       triggers OCR.
    2. An image-only PDF is detected and routed through OCR.
    3. The OCR text flows through the existing cleaning, chunking, embedding,
       FAISS, and metadata pipeline.
    4. The scanned document becomes retrievable after indexing.
    5. The whole upload pipeline still works for a normal text PDF.

The real Tesseract engine is used only when it is installed on the system;
otherwise the OCR step is stubbed so the fallback routing and pipeline
integration are still verified deterministically.

Usage (from backend/):
    python -m app.scripts.test_ocr_fallback

Exit status is non-zero if any check fails.
"""

import asyncio
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import fitz

from app.services.document import Chunker, DocumentService, PDFProcessor
from app.services.document_registry import DocumentRegistry
from app.services.retrieval import BM25Retriever, HybridRetriever
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import SemanticRetriever
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

OWNER = "ocr-owner"

TEXT_PDF_CONTENT = (
    "The quarterly financial report summarizes revenue growth across all "
    "regional divisions."
)
OCR_TEXT = (
    "scanned geothermal schematic annotates basalt reservoir pressure "
    "readings below the observatory."
)
QUERY = "geothermal reservoir readings"


def _make_text_pdf(path: Path, content: str) -> Path:
    """Create a PDF with a selectable text layer."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), content, fontsize=14)
    doc.save(path)
    doc.close()
    return path


def _make_scanned_pdf(path: Path, content: str) -> Path:
    """Create an image-only PDF with no selectable text.

    The content is drawn onto a page, flattened into a raster image, and the
    image is embedded into a fresh page. The resulting PDF has no text layer,
    exactly like a scan.
    """
    source = fitz.open()
    page = source.new_page(width=612, height=792)
    page.insert_text((72, 100), content, fontsize=14)
    image_bytes = page.get_pixmap(dpi=150).tobytes("png")
    source.close()

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_image(page.rect, stream=image_bytes)
    doc.save(path)
    doc.close()
    return path


class FakeEmbeddingService:
    """Deterministic, dependency-free placeholder for EmbeddingService."""

    def __init__(self) -> None:
        self._word_ids: dict[str, int] = {}

    def _vector(self, text: str) -> list[int]:
        words = text.lower().split()
        indexed: list[int] = []
        for word in words:
            word_id = self._word_ids.get(word)
            if word_id is None:
                word_id = len(self._word_ids)
                self._word_ids[word] = word_id
            indexed.append(word_id)
        vector = [0] * len(self._word_ids)
        for word_id in indexed:
            vector[word_id] += 1
        return vector

    def generate_embeddings(self, texts: list[str]) -> list[list[int]]:
        return [self._vector(text) for text in texts]

    def get_embedding_dimension(self) -> int:
        return len(self._word_ids)


def _make_service(
    processor: PDFProcessor,
    embedding_service: FakeEmbeddingService,
    vector_store: VectorStore,
    metadata_store: MetadataStore,
    tmp: Path,
) -> DocumentService:
    return DocumentService(
        pdf_processor=processor,
        chunker=Chunker(chunk_size=10000, chunk_overlap=200),
        embedding_service=embedding_service,
        vector_store=vector_store,
        metadata_store=metadata_store,
        faiss_index_path=str(tmp / "faiss" / "index.faiss"),
        metadata_path=str(tmp / "metadata.json"),
    )


def run_checks() -> list[tuple[str, bool, str]]:
    """Run the OCR fallback checks and return (name, passed, detail)."""
    checks: list[tuple[str, bool, str]] = []

    with TemporaryDirectory() as temp_dir:
        tmp = Path(temp_dir)
        text_pdf = _make_text_pdf(tmp / "text.pdf", TEXT_PDF_CONTENT)
        scanned_pdf = _make_scanned_pdf(tmp / "scan.pdf", TEXT_PDF_CONTENT)

        # Confirm the fixtures behave as intended.
        fixture = fitz.open(scanned_pdf)
        has_text_layer = bool(fixture[0].get_text().strip())
        fixture.close()
        checks.append(
            (
                "(0) scanned fixture has no selectable text",
                not has_text_layer,
                f"selectable text: {has_text_layer!r}",
            )
        )

        # 1. Normal text PDF: existing extraction path, no OCR.
        processor = PDFProcessor()
        with mock.patch.object(
            processor, "_extract_text_with_ocr"
        ) as ocr:
            extracted = processor.extract_text(str(text_pdf))
        checks.append(
            (
                "(1) text PDF extracted without OCR",
                extracted == TEXT_PDF_CONTENT and not ocr.called,
                f"ocr called: {ocr.called}",
            )
        )

        # 2. Scanned PDF: OCR fallback is triggered and its text returned.
        processor = PDFProcessor()
        with mock.patch.object(
            processor,
            "_extract_text_with_ocr",
            side_effect=lambda doc: OCR_TEXT,
        ) as ocr:
            extracted = processor.extract_text(str(scanned_pdf))
        checks.append(
            (
                "(2) scanned PDF routed through OCR",
                ocr.called and extracted == OCR_TEXT.strip(),
                f"ocr called: {ocr.called}",
            )
        )

        # 3. OCR engine availability: clear error without Tesseract, real OCR
        #    otherwise.
        if shutil.which("tesseract"):
            processor = PDFProcessor()
            try:
                extracted = processor.extract_text(str(scanned_pdf))
                passed = bool(extracted.strip())
                detail = f"ocr text length: {len(extracted)}"
            except ValueError as exc:
                passed = False
                detail = f"unexpected error: {exc}"
            checks.append(("(3) real OCR returns text", passed, detail))
        else:
            processor = PDFProcessor()
            try:
                processor.extract_text(str(scanned_pdf))
                passed = False
                detail = "no error raised"
            except ValueError as exc:
                passed = "OCR" in str(exc)
                detail = str(exc)
            checks.append(
                (
                    "(3) missing OCR engine raises a clear error",
                    passed,
                    detail,
                )
            )

        # 4. Pipeline: a scanned document indexed via the real DocumentService
        #    reaches FAISS + metadata and becomes retrievable.
        embedding_service = FakeEmbeddingService()
        embedding_service.generate_embeddings(
            [TEXT_PDF_CONTENT, OCR_TEXT, QUERY]
        )
        vector_store = VectorStore(
            dimension=embedding_service.get_embedding_dimension()
        )
        metadata_store = MetadataStore()
        registry = DocumentRegistry(tmp / "documents.json")
        processor = PDFProcessor()
        with mock.patch.object(
            processor,
            "_extract_text_with_ocr",
            side_effect=lambda doc: OCR_TEXT,
        ) as ocr:
            service = _make_service(
                processor, embedding_service, vector_store, metadata_store, tmp
            )
            result = asyncio.run(
                service.index_document(
                    str(scanned_pdf),
                    workspace_id=DEFAULT_WORKSPACE,
                    document_id="scan-doc",
                    owner_id=OWNER,
                    filename="scan.pdf",
                )
            )
        checks.append(
            (
                "(4a) scanned document indexed via pipeline",
                result.status == "indexed" and result.total_chunks >= 1,
                f"chunks: {result.total_chunks}",
            )
        )
        checks.append(
            (
                "(4b) OCR text reached metadata store",
                any(
                    "geothermal" in record["text"]
                    and "reservoir" in record["text"]
                    for record in metadata_store.get_all_documents()
                ),
                f"metadata records: {len(metadata_store.get_all_documents())}",
            )
        )
        checks.append(
            (
                "(4c) OCR text reached FAISS",
                vector_store.ntotal
                == len(metadata_store.get_all_documents())
                == 1,
                f"ntotal={vector_store.ntotal}",
            )
        )

        bm25 = BM25Retriever(metadata_store, registry)
        hybrid = HybridRetriever(
            semantic_retriever=SemanticRetriever(
                embedding_service,
                vector_store,
                metadata_store,
                registry,
            ),
            bm25_retriever=bm25,
        )
        bm25_hits = {
            item["id"]
            for item in bm25.retrieve(
                QUERY, k=5, workspace_id=DEFAULT_WORKSPACE, owner_id=OWNER
            )
        }
        hybrid_hits = {
            item["id"]
            for item in hybrid.retrieve(
                QUERY, k=5, workspace_id=DEFAULT_WORKSPACE, owner_id=OWNER
            )
        }
        checks.append(
            (
                "(4d) scanned doc retrievable via BM25 without restart",
                1 in bm25_hits,
                f"bm25 ids: {sorted(bm25_hits)}",
            )
        )
        checks.append(
            (
                "(4e) scanned doc retrievable via hybrid without restart",
                1 in hybrid_hits,
                f"hybrid ids: {sorted(hybrid_hits)}",
            )
        )

        # 5. A normal text PDF still follows the unchanged pipeline.
        embedding_service = FakeEmbeddingService()
        embedding_service.generate_embeddings(
            [TEXT_PDF_CONTENT, OCR_TEXT, QUERY]
        )
        vector_store = VectorStore(
            dimension=embedding_service.get_embedding_dimension()
        )
        metadata_store = MetadataStore()
        registry = DocumentRegistry(tmp / "documents-text.json")
        processor = PDFProcessor()
        with mock.patch.object(processor, "_extract_text_with_ocr") as ocr:
            service = _make_service(
                processor, embedding_service, vector_store, metadata_store, tmp
            )
            result = asyncio.run(
                service.index_document(
                    str(text_pdf),
                    workspace_id=DEFAULT_WORKSPACE,
                    document_id="text-doc",
                    owner_id=OWNER,
                    filename="text.pdf",
                )
            )
        checks.append(
            (
                "(5a) text PDF indexed without OCR",
                result.status == "indexed" and not ocr.called,
                f"ocr called: {ocr.called}",
            )
        )
        checks.append(
            (
                "(5b) text PDF chunk is the selectable text",
                any(
                    "financial" in record["text"]
                    for record in metadata_store.get_all_documents()
                ),
                f"metadata records: {len(metadata_store.get_all_documents())}",
            )
        )

        return checks


def print_report(results: list[tuple[str, bool, str]]) -> None:
    """Print the OCR fallback verification report."""
    print("=" * 40)
    print("OCR Fallback Verification")
    print("=" * 40)
    print()
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"{name:<44}{status}")
        if not passed:
            print(f"  {detail}")
    print()
    print("=" * 40)
    print()
    overall = all(passed for _, passed, _ in results)
    print("PASS" if overall else "FAIL")
    print()
    print("=" * 40)
    print()


def main() -> int:
    """Run every OCR fallback check and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    results = run_checks()
    print_report(results)
    overall = all(passed for _, passed, _ in results)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())