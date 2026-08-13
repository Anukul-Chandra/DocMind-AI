from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routes import auth_router, chat_router, documents_router, router
from app.api.retrieve import router as retrieve_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
)

register_exception_handlers(app)

app.include_router(router)
app.include_router(retrieve_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(documents_router)
