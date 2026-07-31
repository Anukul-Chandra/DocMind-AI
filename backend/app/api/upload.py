from fastapi import APIRouter, UploadFile

from app.models.responses import DocumentResponse
from app.services.document_processor import process_document

router = APIRouter()


@router.post("/upload", response_model=DocumentResponse)
async def upload(file: UploadFile):
    chunks = process_document(file)
    return {
        "filename": file.filename,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
