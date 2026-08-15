"""Structured extraction schemas for supported V1 document types.

Each supported document type maps to a pydantic model describing the fields
the LLM extraction layer should produce. Fields are intentionally lenient
(strings and lists with empty defaults) so that partially-recognized documents
still validate; the schema drives both the prompt sent to the provider and the
validation applied to the parsed response.
"""

from pydantic import BaseModel

from app.services.document.classifier import FORM, INVOICE, PASSPORT, RECEIPT, RESUME


class ResumeData(BaseModel):
    """Structured fields extracted from a resume/CV."""

    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    summary: str = ""
    skills: list[str] = []
    work_experience: list[dict] = []
    education: list[dict] = []


class InvoiceData(BaseModel):
    """Structured fields extracted from an invoice."""

    invoice_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    seller_name: str = ""
    buyer_name: str = ""
    total_amount: str = ""
    currency: str = ""
    tax_amount: str = ""
    line_items: list[dict] = []


class ReceiptData(BaseModel):
    """Structured fields extracted from a receipt."""

    receipt_number: str = ""
    store_name: str = ""
    date: str = ""
    payment_method: str = ""
    total_amount: str = ""
    tax_amount: str = ""
    cashier: str = ""
    items: list[dict] = []


class PassportData(BaseModel):
    """Structured fields extracted from a passport or national ID."""

    passport_number: str = ""
    surname: str = ""
    given_names: str = ""
    nationality: str = ""
    date_of_birth: str = ""
    sex: str = ""
    place_of_birth: str = ""
    country_of_issue: str = ""
    date_of_issue: str = ""
    date_of_expiry: str = ""


class FormData(BaseModel):
    """Structured fields extracted from a form."""

    form_name: str = ""
    sections: list[str] = []
    fields: list[str] = []
    signature_required: bool = False
    completed: bool = False


#: Mapping from the classifier's V1 type constants to their extraction schema.
SCHEMAS: dict[str, type[BaseModel]] = {
    RESUME: ResumeData,
    INVOICE: InvoiceData,
    RECEIPT: ReceiptData,
    PASSPORT: PassportData,
    FORM: FormData,
}

#: The set of document types that have an extraction schema.
SUPPORTED_EXTRACTION_TYPES = frozenset(SCHEMAS)