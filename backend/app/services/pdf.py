import fitz

from fastapi import UploadFile


def extract_text_from_pdf(file: UploadFile) -> str:
    """Extract text from an uploaded PDF file.

    Args:
        file: The uploaded PDF file.

    Returns:
        The concatenated text from all pages, stripped of leading/trailing whitespace.
    """
    doc = fitz.open(stream=file.file.read(), filetype="pdf")
    text = "".join(page.get_text() for page in doc)
    doc.close()
    return text.strip()
