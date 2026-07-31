from pydantic import BaseModel


class RetrieveRequest(BaseModel):
    query: str
    k: int = 5


class RetrieveResponse(BaseModel):
    results: list[dict]
