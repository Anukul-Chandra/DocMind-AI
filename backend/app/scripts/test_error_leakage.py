"""Regression tests preventing internal error leakage to API clients.

Verifies that unexpected internal exception details never reach the response
body, while known application errors and status codes are preserved:

    A. An unhandled internal exception returns the generic 500 envelope with
       no internal detail.
    B. A document indexing failure returns a safe 400 message (no underlying
       exception text).
    C. A document registration failure returns a safe 500 message.
    D. An upload file-save failure returns a safe 500 message.
    E. An LLM provider failure on chat returns a safe 502 message.
    F. Known application errors retain their intended messages (404 document,
       400 non-PDF, 401 login failure, 422 validation).

Status codes are asserted alongside every scenario.

Usage (from backend/, JWT_SECRET required to import the app):
    python -m app.scripts.test_error_leakage

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_auth_service,
    get_chat_service,
    get_document_repository,
    get_document_service,
)
from app.api.errors import register_exception_handlers
from app.core.config import settings
from app.main import app as real_app
from app.repositories.json.document_repository import JsonDocumentRepository
from app.repositories.json.user_repository import JsonUserRepository
from app.services.auth import AuthService, JWTService, PasswordService
from app.services.document import Chunker, DocumentService
from app.services.document_registry import DocumentRegistry
from app.services.llm.provider_manager import LLMUnavailableError
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore

PASSWORD = "super-secret-1"
TOKEN_SECRET = "leakage-test-secret"
DIMENSION = 8
UPLOAD_CONTENT = b"%PDF-1.4\nleakage test payload\n" * 40
SAMPLE_TEXT = (
    "DocMind performs semantic retrieval over indexed PDFs with owner scoping "
    "so each user only ever sees their own document chunks."
)

SAFE_INDEX_MESSAGE = "The document could not be indexed. Please ensure the PDF is valid."
SAFE_REGISTER_MESSAGE = "The document was indexed but could not be saved."
SAFE_SAVE_MESSAGE = "The uploaded file could not be saved."
SAFE_CHAT_MESSAGE = (
    "The AI service is temporarily unavailable. Please try again later."
)
GENERIC_500_MESSAGE = "An unexpected error occurred."


class StubPDFProcessor:
    """A PDF processor returning fixed text, optionally failing."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def extract_text(self, file_path: str) -> str:
        if self.fail:
            raise ValueError("simulated extraction failure")
        return SAMPLE_TEXT


class StubEmbeddingService:
    """A deterministic, dependency-free embedding service."""

    def __init__(self, dimension: int = DIMENSION) -> None:
        self._dimension = dimension

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[0.25] * self._dimension for _ in texts]

    def get_embedding_dimension(self) -> int:
        return self._dimension


class RaisingRegisterRepository(JsonDocumentRepository):
    """A repository whose registration step always fails."""

    def register(self, *args, **kwargs):
        raise RuntimeError("simulated registry failure")


class RaisingChatService:
    """A chat service whose underlying provider always fails."""

    async def chat(self, question: str, owner_id: str = "", images=None):
        raise LLMUnavailableError(
            "provider 'openrouter' failed: invalid api key sk-secret123"
        )


def _make_auth(tmp: Path) -> AuthService:
    return AuthService(
        users=JsonUserRepository(tmp / "users.json"),
        passwords=PasswordService(),
        tokens=JWTService(secret_key=TOKEN_SECRET),
    )


def _access_token(user) -> str:
    return JWTService(secret_key=TOKEN_SECRET).create_access_token(user.user_id)


def _build_service(
    processor: StubPDFProcessor,
    metadata_store: MetadataStore,
    vector_store: VectorStore,
    tmp: Path,
) -> DocumentService:
    return DocumentService(
        pdf_processor=processor,
        chunker=Chunker(chunk_size=10000, chunk_overlap=200),
        embedding_service=StubEmbeddingService(),
        vector_store=vector_store,
        metadata_store=metadata_store,
        faiss_index_path=str(tmp / "faiss" / "index.faiss"),
        metadata_path=str(tmp / "metadata.json"),
    )


@contextmanager
def _storage(tmp: Path):
    original = settings.storage_dir
    settings.storage_dir = str(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        yield
    finally:
        settings.storage_dir = original


@contextmanager
def _overrides(overrides: dict):
    for dependency, value in overrides.items():
        real_app.dependency_overrides[dependency] = partial(lambda v: v, value)
    try:
        with TestClient(real_app) as client:
            yield client
    finally:
        real_app.dependency_overrides.clear()


def _upload(client: TestClient, token: str, filename: str = "report.pdf"):
    return client.post(
        "/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, UPLOAD_CONTENT, "application/pdf")},
    )


def main() -> int:
    """Run all leakage scenarios and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    print("=" * 60)
    print("Error Leakage Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    def expect(
        name: str,
        response,
        status_code: int,
        message: str,
        secret: str,
    ) -> None:
        body = response.json()
        body_text = str(body)
        passed = (
            response.status_code == status_code
            and body.get("success") is False
            and body.get("error", {}).get("message") == message
            and secret not in body_text
        )
        detail = f"status={response.status_code}"
        if not passed:
            detail += f" body={body_text}"
        check(name, passed, detail)

    # --- A. Unhandled internal exception -------------------------------
    print("\n[A. Unhandled internal exception]")
    boom_app = FastAPI()
    register_exception_handlers(boom_app)

    @boom_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal trace: SELECT * FROM users WHERE x=1")

    @boom_app.get("/ok")
    def ok() -> dict:
        return {"fine": True}

    with TestClient(boom_app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
        body = response.json()
        check(
            "A. unhandled exception returns safe 500 envelope",
            response.status_code == 500
            and body.get("success") is False
            and body.get("error", {}).get("code") == "internal_server_error"
            and body.get("error", {}).get("message") == GENERIC_500_MESSAGE,
            f"status={response.status_code}",
        )
        check(
            "A. internal detail is absent from the response",
            "secret internal trace" not in str(body),
        )
        check(
            "A. normal requests remain unaffected",
            client.get("/ok").status_code == 200,
        )

    # --- B/C/D. Upload failure paths on the real app --------------------
    print("\n[B/C/D. Upload failure paths]")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # B. Indexing failure (DocumentIndexError -> 400).
        with _storage(tmp / "b"):
            auth = _make_auth(tmp / "b")
            repo = JsonDocumentRepository(
                DocumentRegistry(tmp / "b" / "documents.json")
            )
            service = _build_service(
                StubPDFProcessor(fail=True),
                MetadataStore(),
                VectorStore(DIMENSION),
                tmp / "b",
            )
            user = auth.register("b@example.com", PASSWORD)
            token = _access_token(user)
            with _overrides(
                {
                    get_auth_service: auth,
                    get_document_repository: repo,
                    get_document_service: service,
                }
            ) as client:
                response = _upload(client, token)
            expect(
                "B. indexing failure is a safe 400",
                response,
                400,
                SAFE_INDEX_MESSAGE,
                "simulated extraction failure",
            )

        # C. Registration failure (repository error -> 500).
        with _storage(tmp / "c"):
            auth = _make_auth(tmp / "c")
            repo = RaisingRegisterRepository(
                DocumentRegistry(tmp / "c" / "documents.json")
            )
            service = _build_service(
                StubPDFProcessor(),
                MetadataStore(),
                VectorStore(DIMENSION),
                tmp / "c",
            )
            user = auth.register("c@example.com", PASSWORD)
            token = _access_token(user)
            with _overrides(
                {
                    get_auth_service: auth,
                    get_document_repository: repo,
                    get_document_service: service,
                }
            ) as client:
                response = _upload(client, token)
            expect(
                "C. registration failure is a safe 500",
                response,
                500,
                SAFE_REGISTER_MESSAGE,
                "simulated registry failure",
            )

        # D. File-save failure (OSError -> 500).
        with _storage(tmp / "d"):
            auth = _make_auth(tmp / "d")
            repo = JsonDocumentRepository(
                DocumentRegistry(tmp / "d" / "documents.json")
            )
            service = _build_service(
                StubPDFProcessor(),
                MetadataStore(),
                VectorStore(DIMENSION),
                tmp / "d",
            )
            user = auth.register("d@example.com", PASSWORD)
            token = _access_token(user)
            with mock.patch.object(
                Path,
                "write_bytes",
                side_effect=OSError(
                    "simulated save failure C:\\secret\\internal.pdf"
                ),
            ):
                with _overrides(
                    {
                        get_auth_service: auth,
                        get_document_repository: repo,
                        get_document_service: service,
                    }
                ) as client:
                    response = _upload(client, token)
            expect(
                "D. file-save failure is a safe 500",
                response,
                500,
                SAFE_SAVE_MESSAGE,
                "C:\\secret\\internal.pdf",
            )

    # --- E. Chat LLM provider failure ----------------------------------
    print("\n[E. Chat LLM provider failure]")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        auth = _make_auth(tmp)
        user = auth.register("e@example.com", PASSWORD)
        token = _access_token(user)
        with _overrides(
            {get_auth_service: auth, get_chat_service: RaisingChatService()}
        ) as client:
            response = client.post(
                "/chat/",
                headers={"Authorization": f"Bearer {token}"},
                data={"question": "What is DocMind?"},
            )
        expect(
            "E. provider failure is a safe 502",
            response,
            502,
            SAFE_CHAT_MESSAGE,
            "sk-secret123",
        )

    # --- F. Known application errors retain their messages -------------
    print("\n[F. Known application errors]")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        auth = _make_auth(tmp)
        repo = JsonDocumentRepository(
            DocumentRegistry(tmp / "documents.json")
        )
        user = auth.register("f@example.com", PASSWORD)
        token = _access_token(user)
        with _overrides(
            {get_auth_service: auth, get_document_repository: repo}
        ) as client:
            response = client.get(
                "/documents/does-not-exist",
                headers={"Authorization": f"Bearer {token}"},
            )
            body = response.json()
            check(
                "F. missing document keeps its 404 message",
                response.status_code == 404
                and body.get("error", {}).get("code") == "not_found"
                and body.get("error", {}).get("message") == "Document not found.",
                f"status={response.status_code}",
            )

            response = client.post(
                "/documents/upload",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("notes.txt", b"hello", "text/plain")},
            )
            body = response.json()
            check(
                "F. non-PDF upload keeps its 400 message",
                response.status_code == 400
                and body.get("error", {}).get("message")
                == "Only PDF files are supported.",
                f"status={response.status_code}",
            )

            response = client.post(
                "/auth/login",
                json={"email": "f@example.com", "password": "wrong-password"},
            )
            body = response.json()
            check(
                "F. login failure keeps its 401 message",
                response.status_code == 401
                and body.get("error", {}).get("message")
                == "Invalid email or password.",
                f"status={response.status_code}",
            )

            response = client.post("/auth/login", json={})
            body = response.json()
            check(
                "F. validation failure keeps its 422 message",
                response.status_code == 422
                and body.get("error", {}).get("code") == "validation_error"
                and body.get("error", {}).get("message")
                == "Request validation failed.",
                f"status={response.status_code}",
            )

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(f"Error Leakage Test {'PASSED' if all_passed else 'FAILED'}")
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())