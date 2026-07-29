import fitz

from fastapi import UploadFile, HTTPException


def extract_text_from_pdf(file: UploadFile) -> str:
    """Extract text from an uploaded PDF file.

    Args:
        file: The uploaded PDF file.

    Returns:
        The concatenated text from all pages, stripped of leading/trailing whitespace.
    """
    doc = fitz.open(stream=file.file.read(), filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    file.file.seek(0)
    text = text.strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="The uploaded PDF contains no extractable text.",
        )
    return text
