from fastapi import FastAPI

from app.core.config import APP_NAME, APP_VERSION, APP_DESCRIPTION

app = FastAPI(title=APP_NAME, version=APP_VERSION, description=APP_DESCRIPTION)


@app.get("/")
def root():
    return {"message": "DocMind AI API is running"}
