from fastapi import UploadFile, HTTPException

ALLOWED_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg"}


def validate_upload_file(file: UploadFile) -> None:
    """Validate the content type of an uploaded file.

    Args:
        file: The uploaded file to validate.

    Raises:
        HTTPException: If the file's content type is not supported.
    """
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type.",
        )
