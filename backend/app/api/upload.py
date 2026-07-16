from fastapi import APIRouter, UploadFile

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile):
    return {
        "filename": file.filename,
        "content_type": file.content_type,
    }
