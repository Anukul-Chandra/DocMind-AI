"""Focused regression test for upload filename-collision and size-limit safety.

Two users uploading the same client filename must not overwrite each other's
physical files: the route stores every upload under a server-generated unique
name while preserving the original client filename as display metadata.
Oversized uploads must be rejected before any file or document is created.

The real ``DocumentService`` pipeline is exercised with stub PDF/embedding
collaborators so the route wiring (storage naming, display-filename
propagation, metadata persistence) is verified end to end without loading the
embedding model or touching external services.

Usage (from backend/):
    python -m app.scripts.test_upload_safety

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_auth_service,
    get_document_repository,
    get_document_service,
)
from app.core.config import settings
from app.main import app
from app.repositories.json.document_repository import JsonDocumentRepository
from app.repositories.json.user_repository import JsonUserRepository
from app.services.auth import AuthService, JWTService, PasswordService, User
from app.services.document import Chunker, DocumentService
from app.services.document_registry import DocumentRegistry
from app.services.storage import JsonFileStore
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore

SECRET_PASSWORD = "super-secret-1"
TOKEN_SECRET = "api-test-secret"
SAMPLE_TEXT = (
    "The caribou migration crosses the frozen delta each spring, following "
    "ancient trails of thundering hooves toward the northern calving grounds."
)
A_CONTENT = b"%PDF-1.4\nuser A report payload\n" * 40
B_CONTENT = b"%PDF-1.4\nuser B report payload\n" * 40
BIG_CONTENT = b"x" * 8192


class StubPDFProcessor:
    """A PDF processor that returns fixed text regardless of the file path."""

    def extract_text(self, file_path: str) -> str:
        return SAMPLE_TEXT


class StubEmbeddingService:
    """A deterministic, dependency-free embedding service."""

    def __init__(self, dimension: int = 8) -> None:
        self._dimension = dimension

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self._dimension for _ in texts]

    def get_embedding_dimension(self) -> int:
        return self._dimension


def build_auth_service(users) -> AuthService:
    return AuthService(
        users=users,
        passwords=PasswordService(),
        tokens=JWTService(secret_key=TOKEN_SECRET),
    )


def access_token(user: User) -> str:
    return JWTService(secret_key=TOKEN_SECRET).create_access_token(user.user_id)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def upload(client: TestClient, token: str, content: bytes, filename: str = "report.pdf"):
    return client.post(
        "/documents/upload",
        headers=bearer(token),
        files={"file": (filename, content, "application/pdf")},
    )


def stored_pdf_files(storage_dir: Path) -> list[Path]:
    return sorted(storage_dir.glob("*.pdf"))


def main() -> int:
    """Run the upload safety scenarios."""
    print("=" * 60)
    print("Upload Safety (filename collision + size limit) Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    original_storage_dir = settings.storage_dir
    original_max_upload = settings.max_upload_size_bytes

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            user_repo = JsonUserRepository(tmp / "users.json")
            doc_repo = JsonDocumentRepository(DocumentRegistry(tmp / "documents.json"))
            metadata_store = MetadataStore()
            vector_store = VectorStore(dimension=8)
            document_service = DocumentService(
                pdf_processor=StubPDFProcessor(),
                chunker=Chunker(),
                embedding_service=StubEmbeddingService(),
                vector_store=vector_store,
                metadata_store=metadata_store,
                faiss_index_path=str(tmp / "faiss" / "index.faiss"),
                metadata_path=str(tmp / "metadata.json"),
            )
            auth = build_auth_service(user_repo)
            settings.storage_dir = str(tmp / "uploads")

            app.dependency_overrides[get_auth_service] = lambda: auth
            app.dependency_overrides[get_document_repository] = lambda: doc_repo
            app.dependency_overrides[get_document_service] = lambda: document_service

            with TestClient(app) as client:
                user_a = register_user(auth, "upload.a@example.com")
                user_b = register_user(auth, "upload.b@example.com")
                token_a = access_token(user_a)
                token_b = access_token(user_b)

                # A. User A uploads report.pdf.
                resp_a = upload(client, token_a, A_CONTENT, "report.pdf")
                check(
                    "A. user A upload succeeds",
                    resp_a.status_code == 200 and resp_a.json().get("success") is True,
                )
                doc_a_id = resp_a.json().get("data", {}).get("document_id")

                # B. User B uploads the same filename.
                resp_b = upload(client, token_b, B_CONTENT, "report.pdf")
                check(
                    "B. user B upload succeeds",
                    resp_b.status_code == 200 and resp_b.json().get("success") is True,
                )
                doc_b_id = resp_b.json().get("data", {}).get("document_id")

                # C. Both uploads succeeded and are distinct documents.
                check(
                    "C. both uploads produced distinct documents",
                    bool(doc_a_id) and bool(doc_b_id) and doc_a_id != doc_b_id,
                )

                # F. Original filename preserved in the response.
                check(
                    "F. response filename is report.pdf for both",
                    resp_a.json().get("data", {}).get("filename") == "report.pdf"
                    and resp_b.json().get("data", {}).get("filename") == "report.pdf",
                )

                # D. Physical storage paths are different.
                files = stored_pdf_files(Path(settings.storage_dir))
                check(
                    "D. two distinct physical files exist",
                    len(files) == 2 and files[0] != files[1],
                    f"files={[f.name for f in files]}",
                )

                # E. Neither upload overwrote the other.
                contents = {f.read_bytes() for f in files}
                check(
                    "E. both uploads persisted intact (no overwrite)",
                    A_CONTENT in contents and B_CONTENT in contents,
                )
                check(
                    "E. stored names are server-generated (not report.pdf)",
                    all(f.name != "report.pdf" for f in files),
                    f"names={[f.name for f in files]}",
                )

                # F. Original filename preserved in the repository records.
                reg_a = doc_repo.get_document(doc_a_id, owner_id=user_a.user_id)
                reg_b = doc_repo.get_document(doc_b_id, owner_id=user_b.user_id)
                check(
                    "F. repository filename is report.pdf with correct owners",
                    reg_a is not None
                    and reg_a.filename == "report.pdf"
                    and reg_a.owner_id == user_a.user_id
                    and reg_b is not None
                    and reg_b.filename == "report.pdf"
                    and reg_b.owner_id == user_b.user_id,
                )

                # F. Original filename preserved in chunk metadata (in-memory
                # and on-disk).
                chunk_names = {d["filename"] for d in metadata_store.get_all_documents()}
                check(
                    "F. chunk metadata filename is report.pdf",
                    chunk_names == {"report.pdf"},
                )
                on_disk = JsonFileStore.load(tmp / "metadata.json", default=[])
                check(
                    "F. persisted metadata filename is report.pdf",
                    bool(on_disk)
                    and all(d.get("filename") == "report.pdf" for d in on_disk),
                )

                # K. Ownership isolation still holds.
                other_get = client.get(
                    f"/documents/{doc_a_id}", headers=bearer(token_b)
                )
                check(
                    "K. user B cannot read user A's document",
                    other_get.status_code == 404,
                )
                b_listed = client.get("/documents", headers=bearer(token_b)).json()
                check(
                    "K. user B list omits user A's document",
                    all(
                        d.get("document_id") != doc_a_id
                        for d in b_listed.get("data", [])
                    ),
                )

                # G/H/I. Oversized upload is rejected without side effects.
                settings.max_upload_size_bytes = 1024
                files_before = stored_pdf_files(Path(settings.storage_dir))
                resp_big = upload(client, token_a, BIG_CONTENT, "big.pdf")
                check(
                    "G. oversized upload rejected with 413",
                    resp_big.status_code == 413,
                    f"status={resp_big.status_code}",
                )
                files_after = stored_pdf_files(Path(settings.storage_dir))
                check(
                    "I. rejected upload created no storage file",
                    files_after == files_before,
                )
                check(
                    "H. rejected upload created no document",
                    all(
                        d.filename != "big.pdf"
                        for d in doc_repo.list_documents(owner_id=user_a.user_id)
                    ),
                )

                # J. Normal upload still works after the size-limit test.
                settings.max_upload_size_bytes = original_max_upload
                resp_j = upload(client, token_a, A_CONTENT, "normal.pdf")
                check(
                    "J. normal upload still works",
                    resp_j.status_code == 200
                    and resp_j.json().get("data", {}).get("filename") == "normal.pdf",
                )
    finally:
        app.dependency_overrides.clear()
        settings.storage_dir = original_storage_dir
        settings.max_upload_size_bytes = original_max_upload

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(f"Upload Safety Test {'PASSED' if all_passed else 'FAILED'}")
    print("=" * 60)
    return 0 if all_passed else 1


def register_user(auth: AuthService, email: str) -> User:
    return auth.register(email, SECRET_PASSWORD)


if __name__ == "__main__":
    sys.exit(main())
