from fastapi import UploadFile

from app.services.embedding import EmbeddingService
from app.services.pdf import extract_text_from_pdf, validate_extracted_text
from app.services.chunker import chunk_text
from app.services.text_cleaner import clean_text
from app.services.validation import validate_upload_file


def process_document(file: UploadFile) -> list[str]:
    """Process an uploaded document by validating, extracting, and chunking its text.

    Args:
        file: The uploaded document file.

    Returns:
        A list of text chunks from the document.
    """
    validate_upload_file(file)
    text = extract_text_from_pdf(file)
    validate_extracted_text(text)
    cleaned_text = clean_text(text)
    chunks = chunk_text(cleaned_text)
    embedding_service = EmbeddingService()
    embedding_service.generate_embeddings(chunks)
    return chunks
