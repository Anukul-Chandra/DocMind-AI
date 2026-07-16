from fastapi import FastAPI

from app.api.routes import router
from app.api.upload import router as upload_router
from app.core.config import APP_NAME, APP_VERSION, APP_DESCRIPTION

app = FastAPI(title=APP_NAME, version=APP_VERSION, description=APP_DESCRIPTION)

app.include_router(router)
app.include_router(upload_router)
