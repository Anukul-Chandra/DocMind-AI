"""Focused regression verification of rule-based document classification.

Covers the classifier itself (one realistic fixture per supported V1 type plus
ambiguous/empty text resolving to ``unknown``) and the pipeline integration:

    A. representative invoice text -> invoice
    B. representative resume/CV text -> resume
    C. representative receipt text -> receipt
    D. representative passport/ID text -> passport
    E. representative form text -> form
    F. ambiguous and empty text -> unknown (never classified by filename)
    G. a normal text PDF upload is classified and persisted, and stays
       retrievable
    H. a scanned/OCR PDF upload is classified from the OCR text and stays
       retrievable

All classification uses the extracted text produced by the existing pipeline;
filenames never influence the result.

Usage (from backend/):
    python -m app.scripts.test_document_classification

Exit status is non-zero if any check fails.
"""

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import fitz

from app.repositories.json.document_repository import JsonDocumentRepository
from app.services.document import Chunker, DocumentClassifier, DocumentService
from app.services.document.classifier import (
    FORM,
    INVOICE,
    PASSPORT,
    RECEIPT,
    RESUME,
    UNKNOWN,
)
from app.services.document.pdf_processor import PDFProcessor
from app.services.document_registry import DocumentRegistry
from app.services.retrieval import BM25Retriever, HybridRetriever
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import SemanticRetriever
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

OWNER = "classifier-owner"

INVOICE_TEXT = (
    "INVOICE\n"
    "Invoice Number: INV-2024-0182\n"
    "Bill To: Acme Corporation\n"
    "Consulting services  x10  250.00  2,500.00\n"
    "Subtotal  2,500.00\n"
    "VAT (20%)  500.00\n"
    "Amount Due  3,000.00\n"
    "Payment Terms: Net 30\n"
    "Payment Due By: 2024-03-15\n"
)
RESUME_TEXT = (
    "PROFESSIONAL SUMMARY\n"
    "Experienced software engineer with ten years of experience.\n"
    "WORK EXPERIENCE\n"
    "Senior Engineer at TechCorp, 2019 - present.\n"
    "EDUCATION\n"
    "M.S. Computer Science, State University.\n"
    "SKILLS\n"
    "Python, distributed systems, leadership.\n"
    "CERTIFICATIONS\n"
    "AWS Solutions Architect.\n"
    "REFERENCES\n"
    "Available upon request.\n"
)
RECEIPT_TEXT = (
    "THANK YOU FOR YOUR PURCHASE\n"
    "Store Receipt\n"
    "Transaction ID: TXN-88421\n"
    "Payment Method: Visa ending 4242\n"
    "Amount Paid: $58.32\n"
    "Cashier: Maria\n"
    "Change: $1.68\n"
    "Itemized total before tax: $51.90\n"
)
PASSPORT_TEXT = (
    "PASSPORT\n"
    "Passport Number: P12345678\n"
    "Nationality: CANADIAN\n"
    "Date of Birth: 15 MAR 1990\n"
    "Place of Birth: TORONTO\n"
    "Sex: F\n"
    "Country of Issue: CANADA\n"
)
FORM_TEXT = (
    "APPLICATION FORM\n"
    "Please Complete All Sections\n"
    "Section A: Personal Information\n"
    "Section B: Employment Details\n"
    "Please Provide Two References\n"
    "Signature: ____________________\n"
    "Date of Birth: ______________\n"
    "Official Use Only\n"
)
AMBIGUOUS_TEXT = (
    "The team reviewed the quarterly roadmap and discussed the upcoming "
    "release schedule."
)


def _make_text_pdf(path: Path, content: str) -> Path:
    """Create a PDF with a selectable text layer."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), content, fontsize=12)
    doc.save(path)
    doc.close()
    return path


def _make_scanned_pdf(path: Path, content: str) -> Path:
    """Create an image-only PDF with no selectable text layer."""
    source = fitz.open()
    page = source.new_page(width=612, height=792)
    page.insert_text((72, 100), content, fontsize=12)
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


def _index_and_register(
    service: DocumentService,
    pdf_path: Path,
    metadata_store: MetadataStore,
    registry: DocumentRegistry,
    document_id: str,
    filename: str,
) -> dict:
    """Run the same index + register steps the upload route performs."""
    result = asyncio.run(
        service.index_document(
            str(pdf_path),
            workspace_id=DEFAULT_WORKSPACE,
            document_id=document_id,
            owner_id=OWNER,
            filename=filename,
        )
    )
    document = registry.register(
        DEFAULT_WORKSPACE,
        result.filename,
        result.total_chunks,
        OWNER,
        document_id,
        result.classification,
    )
    return {
        "result": result,
        "document": document,
        "metadata_count": len(metadata_store.get_all_documents()),
    }


def run_checks() -> list[tuple[str, bool, str]]:
    """Run the classification checks and return (name, passed, detail)."""
    checks: list[tuple[str, bool, str]] = []

    classifier = DocumentClassifier()
    fixtures = [
        ("(A) invoice text", INVOICE_TEXT, INVOICE),
        ("(B) resume text", RESUME_TEXT, RESUME),
        ("(C) receipt text", RECEIPT_TEXT, RECEIPT),
        ("(D) passport text", PASSPORT_TEXT, PASSPORT),
        ("(E) form text", FORM_TEXT, FORM),
    ]
    for name, text, expected in fixtures:
        got = classifier.classify(text)
        checks.append((name, got == expected, f"expected {expected}, got {got}"))

    checks.append(
        (
            "(F1) ambiguous text -> unknown",
            classifier.classify(AMBIGUOUS_TEXT) == UNKNOWN,
            f"got {classifier.classify(AMBIGUOUS_TEXT)}",
        )
    )
    checks.append(
        (
            "(F2) empty text -> unknown",
            classifier.classify("") == UNKNOWN
            and classifier.classify("   \n\t  ") == UNKNOWN,
            f"got {classifier.classify('')}",
        )
    )

    with TemporaryDirectory() as temp_dir:
        tmp = Path(temp_dir)
        invoice_pdf = _make_text_pdf(tmp / "report.pdf", INVOICE_TEXT)
        scanned_invoice_pdf = _make_scanned_pdf(
            tmp / "scanned-report.pdf", INVOICE_TEXT
        )

        # G. Normal text PDF: classified from extracted text and persisted.
        embedding_service = FakeEmbeddingService()
        embedding_service.generate_embeddings(
            [INVOICE_TEXT, "amount due", AMBIGUOUS_TEXT]
        )
        vector_store = VectorStore(
            dimension=embedding_service.get_embedding_dimension()
        )
        metadata_store = MetadataStore()
        registry = DocumentRegistry(tmp / "documents.json")
        service = DocumentService(
            pdf_processor=PDFProcessor(),
            chunker=Chunker(chunk_size=10000, chunk_overlap=200),
            embedding_service=embedding_service,
            vector_store=vector_store,
            metadata_store=metadata_store,
            classifier=DocumentClassifier(),
        )
        outcome = _index_and_register(
            service,
            invoice_pdf,
            metadata_store,
            registry,
            "invoice-doc",
            "report.pdf",
        )
        checks.append(
            (
                "(G1) text PDF classified as invoice",
                outcome["result"].classification == INVOICE,
                f"got {outcome['result'].classification}",
            )
        )
        checks.append(
            (
                "(G2) classification persisted in registry",
                outcome["document"].classification == INVOICE,
                f"got {outcome['document'].classification}",
            )
        )
        repo = JsonDocumentRepository(registry)
        checks.append(
            (
                "(G3) classification readable via repository",
                repo.get_document("invoice-doc", OWNER).classification == INVOICE,
                f"got {repo.get_document('invoice-doc', OWNER).classification}",
            )
        )
        # Filename independence: a generic document uploaded as invoice.pdf
        # must stay unknown — classification is driven only by content, never
        # by the filename or path.
        generic_pdf = _make_text_pdf(tmp / "invoice.pdf", AMBIGUOUS_TEXT)
        outcome = _index_and_register(
            service,
            generic_pdf,
            metadata_store,
            registry,
            "generic-doc",
            "invoice.pdf",
        )
        checks.append(
            (
                "(G4) generic content named invoice.pdf stays unknown",
                outcome["result"].classification == UNKNOWN
                and outcome["document"].classification == UNKNOWN,
                f"got {outcome['result'].classification}",
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
        hits = {
            item["id"]
            for item in bm25.retrieve(
                "amount due invoice",
                k=5,
                workspace_id=DEFAULT_WORKSPACE,
                owner_id=OWNER,
            )
        }
        checks.append(
            (
                "(G5) text PDF still retrievable after classification",
                1 in hits,
                f"bm25 ids: {sorted(hits)}",
            )
        )

        # H. Scanned PDF: classified from the OCR text and persisted.
        embedding_service = FakeEmbeddingService()
        embedding_service.generate_embeddings([INVOICE_TEXT, "amount due"])
        vector_store = VectorStore(
            dimension=embedding_service.get_embedding_dimension()
        )
        metadata_store = MetadataStore()
        registry = DocumentRegistry(tmp / "documents-scan.json")
        processor = PDFProcessor()
        with mock.patch.object(
            processor,
            "_extract_text_with_ocr",
            side_effect=lambda doc: INVOICE_TEXT,
        ):
            service = DocumentService(
                pdf_processor=processor,
                chunker=Chunker(chunk_size=10000, chunk_overlap=200),
                embedding_service=embedding_service,
                vector_store=vector_store,
                metadata_store=metadata_store,
                classifier=DocumentClassifier(),
            )
            outcome = _index_and_register(
                service,
                scanned_invoice_pdf,
                metadata_store,
                registry,
                "scan-invoice-doc",
                "scanned-report.pdf",
            )
        checks.append(
            (
                "(H1) scanned/OCR PDF classified as invoice",
                outcome["result"].classification == INVOICE,
                f"got {outcome['result'].classification}",
            )
        )
        checks.append(
            (
                "(H2) scanned/OCR classification persisted in registry",
                outcome["document"].classification == INVOICE,
                f"got {outcome['document'].classification}",
            )
        )
        bm25 = BM25Retriever(metadata_store, registry)
        hits = {
            item["id"]
            for item in bm25.retrieve(
                "invoice amount due",
                k=5,
                workspace_id=DEFAULT_WORKSPACE,
                owner_id=OWNER,
            )
        }
        checks.append(
            (
                "(H3) scanned/OCR doc retrievable after classification",
                1 in hits,
                f"bm25 ids: {sorted(hits)}",
            )
        )

        return checks


def print_report(results: list[tuple[str, bool, str]]) -> None:
    """Print the classification verification report."""
    print("=" * 40)
    print("Document Classification Verification")
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
    """Run every classification check and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    results = run_checks()
    print_report(results)
    overall = all(passed for _, passed, _ in results)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())