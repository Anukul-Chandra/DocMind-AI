from fastapi import FastAPI

app = FastAPI(title="DocMind AI")


@app.get("/")
def root():
    return {"message": "DocMind AI API is running"}
