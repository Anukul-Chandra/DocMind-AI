from fastapi import APIRouter, UploadFile

from app.services.validation import validate_upload_file

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile):
    validate_upload_file(file)
    return {
        "filename": file.filename,
        "content_type": file.content_type,
    }
