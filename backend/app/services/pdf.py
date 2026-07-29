import fitz

from fastapi import UploadFile, HTTPException


def validate_extracted_text(text: str) -> None:
    """Validate that extracted text is not empty after stripping whitespace.

    Args:
        text: The extracted text to validate.

    Raises:
        HTTPException: If the text is empty after stripping.
    """
    if not has_extractable_text(text):
        raise HTTPException(
            status_code=400,
            detail="The uploaded PDF contains no extractable text.",
        )


def has_extractable_text(text: str) -> bool:
    """Check if extracted text contains extractable content after stripping whitespace."""
    return bool(text.strip())


def extract_text_from_pdf(file: UploadFile) -> str:
    """Extract text from an uploaded PDF file.

    Args:
        file: The uploaded PDF file.

    Returns:
        The concatenated text from all pages, stripped of leading/trailing whitespace.
    """
    try:
        doc = fitz.open(stream=file.file.read(), filetype="pdf")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid or corrupted PDF file.",
        )
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    file.file.seek(0)
    text = text.strip()
    validate_extracted_text(text)
    return text
