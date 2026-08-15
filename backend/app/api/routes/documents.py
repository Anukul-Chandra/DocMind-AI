import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status

from app.api.dependencies import (
    get_current_user,
    get_document_repository,
    get_document_service,
)
from app.core.config import settings
from app.models.responses import DeleteResult, SuccessResponse, UploadResult
from app.repositories.interfaces import DocumentRepository
from app.services.auth import User
from app.services.document import DocumentIndexError, DocumentService
from app.services.document.state_snapshot import UploadStateSnapshot
from app.services.document_registry import Document
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=SuccessResponse[UploadResult],
    status_code=status.HTTP_200_OK,
)
async def upload_document(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
    document_repository: DocumentRepository = Depends(get_document_repository),
    workspace_id: str = Query(default=DEFAULT_WORKSPACE),
) -> SuccessResponse[UploadResult]:
    """Upload and automatically index a PDF document for the user.

    Args:
        file: The uploaded PDF file.
        current_user: The authenticated user who owns the document.
        document_service: The service that indexes the uploaded PDF.
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

    content = await _read_upload(file)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    saved_path = _save_upload(file.filename, content)
    document_id = str(uuid4())
    snapshot = document_service.capture_state()

    try:
        result = await document_service.index_document(
            str(saved_path),
            workspace_id=workspace_id,
            document_id=document_id,
            owner_id=current_user.user_id,
            filename=file.filename,
        )
    except DocumentIndexError as exc:
        _compensate_failed_upload(document_service, snapshot, saved_path, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to index document: {exc}",
        ) from exc
    except Exception as exc:
        _compensate_failed_upload(document_service, snapshot, saved_path, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error while indexing: {exc}",
        ) from exc

    try:
        extracted_data = (
            result.extraction.extracted
            if result.extraction is not None
            else None
        )
        document = document_repository.register(
            workspace_id=workspace_id,
            filename=result.filename,
            chunk_count=result.total_chunks,
            owner_id=current_user.user_id,
            document_id=document_id,
            classification=result.classification,
            extracted_data=extracted_data,
        )
    except Exception as exc:
        _compensate_failed_upload(document_service, snapshot, saved_path, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register document: {exc}",
        ) from exc

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
    current_user: User = Depends(get_current_user),
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> SuccessResponse[list[Document]]:
    """Return the documents owned by the authenticated user.

    Args:
        current_user: The authenticated user.
        document_repository: The repository of indexed documents.

    Returns:
        A success envelope with the user's documents.
    """
    return SuccessResponse(
        data=document_repository.list_documents(owner_id=current_user.user_id)
    )


@router.get("/{document_id}", response_model=SuccessResponse[Document])
def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> SuccessResponse[Document]:
    """Return a single indexed document owned by the user.

    Args:
        document_id: The document identifier.
        current_user: The authenticated user.
        document_repository: The repository of indexed documents.

    Returns:
        A success envelope with the matching document.

    Raises:
        HTTPException: If the document does not exist or belongs to another
            user. The response does not reveal which case occurred.
    """
    document = document_repository.get_document(
        document_id, owner_id=current_user.user_id
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    return SuccessResponse(data=document)


@router.delete("/{document_id}", response_model=SuccessResponse[DeleteResult])
def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> SuccessResponse[DeleteResult]:
    """Mark a document owned by the user as deleted.

    The FAISS vectors are not removed; only the registry entry is marked.

    Args:
        document_id: The document identifier.
        current_user: The authenticated user.
        document_repository: The repository of indexed documents.

    Returns:
        A success envelope describing the deletion outcome.

    Raises:
        HTTPException: If the document does not exist, is already deleted, or
            belongs to another user. The response does not reveal which case
            occurred.
    """
    if not document_repository.delete_document(
        document_id, owner_id=current_user.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or already deleted.",
        )
    return SuccessResponse(
        data=DeleteResult(document_id=document_id, status="deleted")
    )


_UPLOAD_READ_CHUNK_SIZE = 1024 * 1024


def _compensate_failed_upload(
    document_service: DocumentService,
    snapshot: UploadStateSnapshot,
    saved_path: Path,
    original_exception: BaseException,
) -> None:
    """Roll back every side effect of a failed upload request.

    The pre-upload FAISS and metadata state (in-memory and persisted) is
    restored, the restored FAISS index is persisted atomically, and only the
    physical PDF created by this request is deleted. Cleanup failures are
    logged and never replace the original exception, and no file other than
    ``saved_path`` is ever touched.

    Args:
        document_service: The service that holds the mutated stores.
        snapshot: The pre-upload state captured before indexing.
        saved_path: The physical PDF file created by this request.
        original_exception: The exception that caused the rollback, used for
            logging context only.
    """
    try:
        document_service.restore_state(snapshot)
    except Exception as exc:  # noqa: BLE001 - cleanup must never mask the original error
        logger.error(
            "Failed to restore pre-upload state after upload error; "
            "original error: %r, restore error: %r",
            original_exception,
            exc,
        )
    try:
        saved_path.unlink()
    except OSError as exc:
        logger.error(
            "Failed to delete upload file %s after upload error; "
            "original error: %r, cleanup error: %r",
            saved_path,
            original_exception,
            exc,
        )


async def _read_upload(file: UploadFile) -> bytes:
    """Read an uploaded file into memory with a bounded size limit.

    The file is read in fixed-size chunks so the full payload is never buffered
    before its size is checked: as soon as the cumulative size exceeds
    ``settings.max_upload_size_bytes`` the request is rejected without reading
    any further. A best-effort pre-check on ``UploadFile.size`` (when the
    framework exposes it) rejects oversized uploads without reading at all.

    Args:
        file: The uploaded file.

    Returns:
        The complete file content as bytes.

    Raises:
        HTTPException: With status 413 if the upload exceeds the configured
            maximum upload size.
    """
    file_size = getattr(file, "size", None)
    if file_size is not None and file_size > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                "Upload exceeds the maximum allowed size of "
                f"{settings.max_upload_size_bytes} bytes."
            ),
        )

    content = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_SIZE)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    "Upload exceeds the maximum allowed size of "
                    f"{settings.max_upload_size_bytes} bytes."
                ),
            )
    return bytes(content)


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

    The physical storage filename is server-generated (a random suffix plus the
    original extension) so that two users uploading the same client filename
    never overwrite each other's files. The original ``filename`` is used only
    to derive the extension, never as the storage name.

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
        suffix = Path(filename).suffix.lower()
        destination = storage_dir / f"{uuid4().hex}{suffix}"
        destination.write_bytes(content)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {exc}",
        ) from exc
    return destination
