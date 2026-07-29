from fastapi import UploadFile

from app.services.pdf import extract_text_from_pdf, validate_extracted_text
from app.services.text_cleaner import clean_text
from app.services.validation import validate_upload_file


def process_document(file: UploadFile) -> str:
    """Process an uploaded document by validating and extracting its text.

    Args:
        file: The uploaded document file.

    Returns:
        The extracted text from the document.
    """
    validate_upload_file(file)
    text = extract_text_from_pdf(file)
    validate_extracted_text(text)
    cleaned_text = clean_text(text)
    return cleaned_text
