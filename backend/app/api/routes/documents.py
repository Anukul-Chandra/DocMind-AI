from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status

from app.api.dependencies import (
    get_document_index_service,
    get_document_repository,
)
from app.core.config import settings
from app.models.responses import DeleteResult, SuccessResponse, UploadResult
from app.repositories.interfaces import DocumentRepository
from app.services.document_registry import Document
from app.services.indexing import DocumentIndexError, DocumentIndexService
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=SuccessResponse[UploadResult],
    status_code=status.HTTP_200_OK,
)
async def upload_document(
    file: UploadFile,
    document_index_service: DocumentIndexService = Depends(get_document_index_service),
    document_repository: DocumentRepository = Depends(get_document_repository),
    workspace_id: str = Query(default=DEFAULT_WORKSPACE),
) -> SuccessResponse[UploadResult]:
    """Upload and automatically index a PDF document.

    Args:
        file: The uploaded PDF file.
        document_index_service: The service that indexes the uploaded PDF.
        document_repository: Persists the indexed document for management.
        workspace_id: The workspace the document belongs to.

    Returns:
        A success envelope summarizing the indexed document.

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
    document_id = str(uuid4())

    try:
        result = document_index_service.index_document(
            str(saved_path),
            workspace_id=workspace_id,
            document_id=document_id,
        )
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

    document = document_repository.register(
        workspace_id=workspace_id,
        filename=result.filename,
        chunk_count=result.total_chunks,
        document_id=document_id,
    )

    return SuccessResponse(
        data=UploadResult(
            document_id=document.document_id,
            workspace_id=document.workspace_id,
            filename=document.filename,
            chunks=result.total_chunks,
            embeddings=result.total_embeddings,
            status="indexed",
        )
    )


@router.get("", response_model=SuccessResponse[list[Document]])
def list_documents(
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> SuccessResponse[list[Document]]:
    """Return all indexed documents.

    Args:
        document_repository: The repository of indexed documents.

    Returns:
        A success envelope with all registered documents.
    """
    return SuccessResponse(data=document_repository.list_documents())


@router.get("/{document_id}", response_model=SuccessResponse[Document])
def get_document(
    document_id: str,
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> SuccessResponse[Document]:
    """Return a single indexed document.

    Args:
        document_id: The document identifier.
        document_repository: The repository of indexed documents.

    Returns:
        A success envelope with the matching document.

    Raises:
        HTTPException: If the document does not exist.
    """
    document = document_repository.get_document(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    return SuccessResponse(data=document)


@router.delete("/{document_id}", response_model=SuccessResponse[DeleteResult])
def delete_document(
    document_id: str,
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> SuccessResponse[DeleteResult]:
    """Mark a document as deleted so retrieval and chat ignore it.

    The FAISS vectors are not removed; only the registry entry is marked.

    Args:
        document_id: The document identifier.
        document_repository: The repository of indexed documents.

    Returns:
        A success envelope describing the deletion outcome.

    Raises:
        HTTPException: If the document does not exist or is already deleted.
    """
    if not document_repository.delete_document(document_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or already deleted.",
        )
    return SuccessResponse(
        data=DeleteResult(document_id=document_id, status="deleted")
    )


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