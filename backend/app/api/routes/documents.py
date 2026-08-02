from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.api.dependencies import get_document_index_service
from app.core.config import settings
from app.services.indexing import DocumentIndexError, DocumentIndexService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", status_code=status.HTTP_200_OK)
async def upload_document(
    file: UploadFile,
    document_index_service: DocumentIndexService = Depends(get_document_index_service),
) -> dict[str, object]:
    """Upload and automatically index a PDF document.

    Args:
        file: The uploaded PDF file.
        document_index_service: The service that indexes the uploaded PDF.

    Returns:
        A dict summarizing the indexed document.

    Raises:
        HTTPException: If the file is invalid, cannot be saved, or cannot be indexed.
    """
    if not _is_pdf(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    saved_path = _save_upload(file.filename, content)

    try:
        result = document_index_service.index_document(str(saved_path))
    except DocumentIndexError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to index document: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error while indexing: {exc}",
        ) from exc

    return {
        "filename": result.filename,
        "chunks": result.total_chunks,
        "embeddings": result.total_embeddings,
        "status": "indexed",
    }


def _is_pdf(filename: str | None) -> bool:
    """Check whether a filename has a PDF extension.

    Args:
        filename: The filename to check.

    Returns:
        True if the filename ends with a .pdf extension, otherwise False.
    """
    return bool(filename and filename.lower().endswith(".pdf"))


def _save_upload(filename: str, content: bytes) -> Path:
    """Persist the uploaded file into the configured storage directory.

    Args:
        filename: The original name of the uploaded file.
        content: The raw bytes of the uploaded file.

    Returns:
        The path where the file was saved.

    Raises:
        HTTPException: If the file cannot be written to disk.
    """
    storage_dir = Path(settings.storage_dir)
    try:
        storage_dir.mkdir(parents=True, exist_ok=True)
        destination = storage_dir / Path(filename).name
        destination.write_bytes(content)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {exc}",
        ) from exc
    return destination