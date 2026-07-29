from fastapi import APIRouter, UploadFile

from app.services.document_processor import process_document

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile):
    extracted_text = process_document(file)
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "text": extracted_text,
    }
