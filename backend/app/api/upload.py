from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.dependencies import get_indexing_service
from app.models.responses import DocumentResponse
from app.services.document_processor import process_document
from app.services.indexing import IndexingService

router = APIRouter()


@router.post("/upload", response_model=DocumentResponse)
async def upload(
    file: UploadFile,
    indexing_service: IndexingService = Depends(get_indexing_service),
):
    chunks = process_document(file)
    try:
        indexing_service.index_document(chunks, file.filename)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to index document")
    return {
        "filename": file.filename,
        "chunk_count": len(chunks),
        "chunks": [
            {"id": index, "text": chunk}
            for index, chunk in enumerate(chunks, start=1)
        ],
    }
