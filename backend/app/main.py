from fastapi import FastAPI

from app.api.routes import router
from app.api.retrieve import router as retrieve_router
from app.api.upload import router as upload_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
)

app.include_router(router)
app.include_router(upload_router)
app.include_router(retrieve_router)
