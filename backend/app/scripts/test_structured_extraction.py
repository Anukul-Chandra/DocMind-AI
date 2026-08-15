"""Focused regression verification of structured information extraction.

Covers the extraction layer itself plus its integration in the indexing
pipeline, using a fake provider manager so results are deterministic:

    1. each supported document type selects the correct extraction schema
    2. representative text produces validated structured output (one case per
       supported type, including a markdown-fenced and a prose-prefixed
       response)
    3. malformed/empty model output is handled safely (invalid JSON, arrays,
       strings, null, prose, empty text, and an unavailable provider) without
       raising
    4. unknown documents are never forced through a known type and the
       provider is never called for them
    5. OCR-derived text (scanned PDF) flows through extraction and the
       extracted data is persisted and retrievable
    6. the normal upload/index/retrieval pipeline still works with the
       extractor wired in

Usage (from backend/):
    python -m app.scripts.test_structured_extraction

Exit status is non-zero if any check fails.
"""

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import fitz

from app.models.llm import LLMResponse
from app.services.document import Chunker, DocumentClassifier, DocumentService
from app.services.document.classifier import (
    FORM,
    INVOICE,
    PASSPORT,
    RECEIPT,
    RESUME,
    UNKNOWN,
)
from app.services.document.extraction import (
    EMPTY,
    EXTRACTED,
    INVALID,
    SKIPPED,
    UNAVAILABLE,
    ExtractionService,
)
from app.services.document.extraction.schemas import (
    SCHEMAS,
    FormData,
    InvoiceData,
    PassportData,
    ReceiptData,
    ResumeData,
)
from app.services.document.pdf_processor import PDFProcessor
from app.services.document_registry import DocumentRegistry
from app.services.llm.provider_manager import LLMUnavailableError
from app.services.retrieval import BM25Retriever
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

OWNER = "extraction-owner"

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
    "Signature: ____________________\n"
    "Official Use Only\n"
)
AMBIGUOUS_TEXT = (
    "The team reviewed the quarterly roadmap and discussed the upcoming "
    "release schedule."
)

VALID_RESPONSES = {
    RESUME: {
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "555-0100",
        "skills": ["Python", "Distributed Systems"],
        "work_experience": [{"title": "Senior Engineer", "company": "TechCorp"}],
        "education": [{"degree": "M.S. Computer Science"}],
    },
    INVOICE: {
        "invoice_number": "INV-2024-0182",
        "invoice_date": "2024-02-20",
        "seller_name": "Consulting Services Inc.",
        "buyer_name": "Acme Corporation",
        "total_amount": "3000.00",
        "currency": "USD",
        "line_items": [{"description": "Consulting services", "amount": "2500.00"}],
    },
    RECEIPT: {
        "receipt_number": "TXN-88421",
        "store_name": "Corner Store",
        "total_amount": "58.32",
        "payment_method": "Visa",
        "cashier": "Maria",
    },
    PASSPORT: {
        "passport_number": "P12345678",
        "surname": "DOE",
        "given_names": "JANE",
        "nationality": "CANADIAN",
        "date_of_birth": "15 MAR 1990",
    },
    FORM: {
        "form_name": "Application",
        "sections": ["Personal Information", "Employment Details"],
        "signature_required": True,
        "completed": False,
    },
}


class FakeProviderManager:
    """In-memory ProviderManager replacement returning scripted responses."""

    def __init__(self, response_text: str = "", raise_unavailable: bool = False):
        self._response_text = response_text
        self._raise_unavailable = raise_unavailable
        self.calls: list[dict] = []

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if self._raise_unavailable:
            raise LLMUnavailableError("all providers failed")
        return LLMResponse(
            text=self._response_text,
            provider="FakeProvider",
            model="fake-model",
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


def run_checks() -> list[tuple[str, bool, str]]:
    """Run the extraction checks and return (name, passed, detail)."""
    checks: list[tuple[str, bool, str]] = []

    # 1. Schema selection per supported document type.
    expected_schemas = {
        RESUME: ResumeData,
        INVOICE: InvoiceData,
        RECEIPT: ReceiptData,
        PASSPORT: PassportData,
        FORM: FormData,
    }
    for doc_type, schema_cls in expected_schemas.items():
        checks.append(
            (
                f"(1) {doc_type} selects {schema_cls.__name__}",
                SCHEMAS.get(doc_type) is schema_cls,
                f"got {SCHEMAS.get(doc_type)}",
            )
        )
    checks.append(
        (
            "(1) unknown has no extraction schema",
            UNKNOWN not in SCHEMAS,
            f"got {SCHEMAS.get(UNKNOWN)}",
        )
    )

    # 2. Representative text produces validated structured output per type.
    for doc_type, fixture in [
        (RESUME, RESUME_TEXT),
        (INVOICE, INVOICE_TEXT),
        (RECEIPT, RECEIPT_TEXT),
        (PASSPORT, PASSPORT_TEXT),
        (FORM, FORM_TEXT),
    ]:
        expected = VALID_RESPONSES[doc_type]
        response = json.dumps(expected)
        if doc_type == INVOICE:
            response = f"```json\n{response}\n```"
        provider = FakeProviderManager(response)
        service = ExtractionService(provider)
        result = asyncio.run(service.extract(fixture, doc_type))
        checks.append(
            (
                f"(2) {doc_type} text extracts validated output",
                result.status == EXTRACTED
                and result.document_type == doc_type
                and result.extracted is not None
                and result.extracted.get("provider") is None,
                f"status={result.status}, document_type={result.document_type}",
            )
        )
        expected_key = {
            RESUME: "email",
            INVOICE: "invoice_number",
            RECEIPT: "receipt_number",
            PASSPORT: "passport_number",
            FORM: "form_name",
        }[doc_type]
        checks.append(
            (
                f"(2) {doc_type} extracted field '{expected_key}'",
                result.extracted is not None
                and result.extracted.get(expected_key)
                == expected[expected_key],
                f"got {result.extracted and result.extracted.get(expected_key)}",
            )
        )
        checks.append(
            (
                f"(2) {doc_type} request used temperature 0 and the schema",
                len(provider.calls) == 1
                and provider.calls[0]["temperature"] == 0.0
                and "JSON" in (provider.calls[0]["system_prompt"] or "")
                and doc_type in (provider.calls[0]["system_prompt"] or ""),
                f"calls={len(provider.calls)}",
            )
        )

    # Prose-prefixed response resolves via the object fallback.
    provider = FakeProviderManager(
        'Here is the data: {"invoice_number": "INV-9", "total_amount": "10.00"}'
    )
    result = asyncio.run(ExtractionService(provider).extract(INVOICE_TEXT, INVOICE))
    checks.append(
        (
            "(2) prose-prefixed JSON is still parsed",
            result.status == EXTRACTED
            and result.extracted is not None
            and result.extracted["invoice_number"] == "INV-9",
            f"status={result.status}",
        )
    )

    # 3. Malformed/empty model output is handled safely.
    malformed_cases = [
        ("empty response", ""),
        ("whitespace response", "   \n   "),
        ("prose response", "I cannot extract this document."),
        ("broken json", '{"invoice_number": "INV-1", total_amount: "10"}'),
        ("array json", "[1, 2, 3]"),
        ("string json", '"hello"'),
        ("null json", "null"),
    ]
    for label, response in malformed_cases:
        provider = FakeProviderManager(response)
        result = asyncio.run(
            ExtractionService(provider).extract(INVOICE_TEXT, INVOICE)
        )
        checks.append(
            (
                f"(3) {label} -> invalid, no data, no raise",
                result.status == INVALID
                and result.extracted is None
                and bool(result.error),
                f"status={result.status}, extracted={result.extracted}",
            )
        )
    provider = FakeProviderManager(raise_unavailable=True)
    result = asyncio.run(ExtractionService(provider).extract(INVOICE_TEXT, INVOICE))
    checks.append(
        (
            "(3) provider failure -> unavailable, no data, no raise",
            result.status == UNAVAILABLE
            and result.extracted is None
            and bool(result.error),
            f"status={result.status}",
        )
    )

    # Empty document text for a known type short-circuits before the provider.
    provider = FakeProviderManager('{"invoice_number": "x"}')
    result = asyncio.run(ExtractionService(provider).extract("   ", INVOICE))
    checks.append(
        (
            "(3) empty document text -> empty, provider never called",
            result.status == EMPTY and provider.calls == [],
            f"status={result.status}, calls={len(provider.calls)}",
        )
    )

    # 4. Unknown documents are never extracted or sent to a provider.
    provider = FakeProviderManager('{"invoice_number": "x"}')
    result = asyncio.run(ExtractionService(provider).extract(AMBIGUOUS_TEXT, UNKNOWN))
    checks.append(
        (
            "(4) unknown document skipped, provider never called",
            result.status == SKIPPED
            and result.document_type == UNKNOWN
            and result.extracted is None
            and provider.calls == [],
            f"status={result.status}, calls={len(provider.calls)}",
        )
    )

    # 5. OCR-derived text is extracted; 6. the pipeline still works end to end.
    with TemporaryDirectory() as temp_dir:
        tmp = Path(temp_dir)
        scanned_invoice_pdf = _make_scanned_pdf(tmp / "scanned.pdf", INVOICE_TEXT)

        embedding_service = FakeEmbeddingService()
        embedding_service.generate_embeddings(
            [INVOICE_TEXT, "amount due", AMBIGUOUS_TEXT]
        )
        vector_store = VectorStore(
            dimension=embedding_service.get_embedding_dimension()
        )
        metadata_store = MetadataStore()
        registry = DocumentRegistry(tmp / "documents.json")
        processor = PDFProcessor()
        provider = FakeProviderManager(
            json.dumps(VALID_RESPONSES[INVOICE])
        )
        service = DocumentService(
            pdf_processor=processor,
            chunker=Chunker(chunk_size=10000, chunk_overlap=200),
            embedding_service=embedding_service,
            vector_store=vector_store,
            metadata_store=metadata_store,
            classifier=DocumentClassifier(),
            extractor=ExtractionService(provider),
        )
        with mock.patch.object(
            processor,
            "_extract_text_with_ocr",
            side_effect=lambda doc: INVOICE_TEXT,
        ):
            result = asyncio.run(
                service.index_document(
                    str(scanned_invoice_pdf),
                    workspace_id=DEFAULT_WORKSPACE,
                    document_id="scan-invoice-doc",
                    owner_id=OWNER,
                    filename="scanned.pdf",
                )
            )
        checks.append(
            (
                "(5) OCR-derived text classified as invoice",
                result.classification == INVOICE,
                f"got {result.classification}",
            )
        )
        checks.append(
            (
                "(5) OCR-derived text produced extracted data",
                result.extraction is not None
                and result.extraction.status == EXTRACTED
                and result.extraction.extracted is not None
                and result.extraction.extracted["invoice_number"]
                == "INV-2024-0182",
                f"status={result.extraction and result.extraction.status}",
            )
        )
        document = registry.register(
            DEFAULT_WORKSPACE,
            result.filename,
            result.total_chunks,
            OWNER,
            "scan-invoice-doc",
            result.classification,
            result.extraction.extracted if result.extraction else None,
        )
        checks.append(
            (
                "(5) extracted data persisted in registry",
                document.extracted_data is not None
                and document.extracted_data["invoice_number"] == "INV-2024-0182",
                f"got {document.extracted_data}",
            )
        )
        reloaded = DocumentRegistry(tmp / "documents.json")
        reloaded_doc = reloaded.get_document("scan-invoice-doc", OWNER)
        checks.append(
            (
                "(5) extracted data survives registry reload",
                reloaded_doc is not None
                and reloaded_doc.extracted_data is not None
                and reloaded_doc.extracted_data["invoice_number"] == "INV-2024-0182",
                f"got {reloaded_doc and reloaded_doc.extracted_data}",
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
                "(5) scanned/OCR doc retrievable after extraction",
                1 in hits,
                f"bm25 ids: {sorted(hits)}",
            )
        )

        # A generic upload with an invoice-like name stays unknown and never
        # reaches the provider.
        generic_pdf = _make_text_pdf(tmp / "invoice.pdf", AMBIGUOUS_TEXT)
        provider = FakeProviderManager("{}")
        service = DocumentService(
            pdf_processor=PDFProcessor(),
            chunker=Chunker(chunk_size=10000, chunk_overlap=200),
            embedding_service=embedding_service,
            vector_store=vector_store,
            metadata_store=metadata_store,
            classifier=DocumentClassifier(),
            extractor=ExtractionService(provider),
        )
        result = asyncio.run(
            service.index_document(
                str(generic_pdf),
                workspace_id=DEFAULT_WORKSPACE,
                document_id="generic-doc",
                owner_id=OWNER,
                filename="invoice.pdf",
            )
        )
        checks.append(
            (
                "(6) generic content named invoice.pdf stays unknown",
                result.classification == UNKNOWN
                and result.extraction is not None
                and result.extraction.status == SKIPPED
                and result.extraction.extracted is None
                and provider.calls == [],
                f"classification={result.classification}, calls={len(provider.calls)}",
            )
        )

        return checks


def print_report(results: list[tuple[str, bool, str]]) -> None:
    """Print the extraction verification report."""
    print("=" * 40)
    print("Structured Extraction Verification")
    print("=" * 40)
    print()
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"{name:<56}{status}")
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
    """Run every extraction check and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    results = run_checks()
    print_report(results)
    overall = all(passed for _, passed, _ in results)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())