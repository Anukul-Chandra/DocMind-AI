"""Regression test for safe upload failure compensation (Part 2).

Drives the real ``POST /documents/upload`` route with isolated, controllable
collaborators and verifies that a failed upload restores the exact pre-upload
logical state:

    A. Successful upload works normally.
    B. Indexing failure: PDF removed, registry/metadata/FAISS unchanged, and
       the persisted FAISS index restored.
    C. Metadata persistence failure: the same rollback guarantees.
    D. Registry failure: the same rollback guarantees.
    E. An existing document survives a failed second upload.
    F. A cleanup (PDF deletion) failure never replaces the original exception.
    G. The consistency checker reports the same state before and after a
       failed upload.
    H. The compensation works through the DocumentRepository abstraction with
       the SQLite-backed PostgreSQL repository code path.

All scenarios run on temporary isolated paths; the real backend/storage files
are never touched.

Usage (from backend/):
    python -m app.scripts.test_upload_failure_compensation

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import (
    get_auth_service,
    get_document_repository,
    get_document_service,
)
from app.core.config import settings
from app.db import models as db  # noqa: F401  (register tables on Base.metadata)
from app.db.base import Base
from app.main import app
from app.repositories.json.document_repository import JsonDocumentRepository
from app.repositories.json.user_repository import JsonUserRepository
from app.repositories.postgres.document_repository import PostgresDocumentRepository
from app.services.auth import AuthService, JWTService, PasswordService
from app.services.document import Chunker, DocumentService
from app.services.document.consistency import check_consistency
from app.services.document_registry import DocumentRegistry
from app.services.storage import JsonFileStore
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

DIMENSION = 8
PASSWORD = "super-secret-1"
TOKEN_SECRET = "compensation-test-secret"
SAMPLE_TEXT = (
    "DocMind performs semantic retrieval over indexed PDFs with owner scoping "
    "so each user only ever sees their own document chunks."
)
UPLOAD_CONTENT = b"%PDF-1.4\ncompensation test payload\n" * 40


class StubPDFProcessor:
    """A PDF processor that returns fixed text, optionally failing."""

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


class FailingMetadataStore(MetadataStore):
    """A MetadataStore whose persistence step always fails."""

    def save(self, path: str) -> None:
        raise OSError("simulated metadata write failure")


class RaisingRegisterRepository(JsonDocumentRepository):
    """A repository whose registration step always fails."""

    def register(
        self,
        workspace_id: str,
        filename: str,
        chunk_count: int,
        owner_id: str,
        document_id: str | None = None,
    ):
        raise RuntimeError("simulated registry failure")


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


def _seed_existing(
    vector_store: VectorStore,
    metadata_store: MetadataStore,
    faiss_path: Path,
    metadata_path: Path,
    registry: DocumentRegistry,
) -> None:
    vector_store.add_embeddings([[0.1] * DIMENSION])
    metadata_store.add_documents(
        ["existing chunk"], "existing.pdf", DEFAULT_WORKSPACE, "doc-existing", "alice"
    )
    vector_store.save(str(faiss_path))
    JsonFileStore.save(metadata_path, metadata_store.snapshot_documents())
    registry.register(
        DEFAULT_WORKSPACE, "existing.pdf", 1, "alice", document_id="doc-existing"
    )


@contextmanager
def _storage(tmp: Path):
    original = settings.storage_dir
    settings.storage_dir = str(tmp / "uploads")
    (tmp / "uploads").mkdir(parents=True, exist_ok=True)
    try:
        yield
    finally:
        settings.storage_dir = original


@contextmanager
def _overrides(auth, repo, service):
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.dependency_overrides[get_document_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _upload(client: TestClient, token: str, filename: str = "report.pdf"):
    return client.post(
        "/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, UPLOAD_CONTENT, "application/pdf")},
    )


def _faiss_disk(faiss_path: Path) -> int:
    return VectorStore.load(str(faiss_path), DIMENSION).ntotal


def _meta_disk(metadata_path: Path) -> list:
    return JsonFileStore.load(metadata_path, default=[])


def _registry_ids(repo) -> list[str]:
    return sorted(document.document_id for document in repo.list_all_documents())


def _pdf_files() -> list[Path]:
    return sorted(Path(settings.storage_dir).glob("*.pdf"))


def _state(vector_store, metadata_store, faiss_path, metadata_path, repo) -> dict:
    return {
        "faiss_mem": vector_store.ntotal,
        "faiss_disk": _faiss_disk(faiss_path),
        "meta_mem": metadata_store.snapshot_documents(),
        "meta_disk": _meta_disk(metadata_path),
        "registry": _registry_ids(repo),
        "pdfs": len(_pdf_files()),
    }


def _check_restored(check, label: str, before: dict, after: dict) -> None:
    check(f"{label} pdf removed", after["pdfs"] == before["pdfs"])
    check(f"{label} registry unchanged", after["registry"] == before["registry"])
    check(
        f"{label} metadata memory restored",
        after["meta_mem"] == before["meta_mem"],
    )
    check(f"{label} metadata disk restored", after["meta_disk"] == before["meta_disk"])
    check(
        f"{label} FAISS memory restored",
        after["faiss_mem"] == before["faiss_mem"],
    )
    check(
        f"{label} FAISS disk restored",
        after["faiss_disk"] == before["faiss_disk"],
    )


def main() -> int:
    """Run the upload compensation scenarios."""
    print("=" * 60)
    print("Upload Failure Compensation Test")
    print("=" * 60)

    checks: dict[str, bool] = {"failed": False}

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        if not passed:
            checks["failed"] = True

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # A. Successful upload works normally.
        with _storage(tmp / "a"):
            auth = _make_auth(tmp / "a")
            registry = DocumentRegistry(tmp / "a" / "documents.json")
            repo = JsonDocumentRepository(registry)
            vector_store = VectorStore(DIMENSION)
            metadata_store = MetadataStore()
            service = _build_service(
                StubPDFProcessor(), metadata_store, vector_store, tmp / "a"
            )
            user = auth.register("a@example.com", PASSWORD)
            token = _access_token(user)
            with _overrides(auth, repo, service) as client:
                resp = _upload(client, token)
                check(
                    "A. successful upload returns 200",
                    resp.status_code == 200 and resp.json().get("success") is True,
                    f"status={resp.status_code}",
                )
                doc_id = resp.json().get("data", {}).get("document_id")
                check(
                    "A. document registered",
                    bool(doc_id) and doc_id in _registry_ids(repo),
                )
                check("A. pdf persisted", len(_pdf_files()) == 1)
                check(
                    "A. FAISS memory == metadata count",
                    vector_store.ntotal
                    == len(metadata_store.get_all_documents())
                    == 1,
                )
                check(
                    "A. FAISS disk == metadata disk",
                    _faiss_disk(tmp / "a" / "faiss" / "index.faiss")
                    == len(_meta_disk(tmp / "a" / "metadata.json"))
                    == 1,
                )

        # B. Indexing failure.
        with _storage(tmp / "b"):
            auth = _make_auth(tmp / "b")
            registry = DocumentRegistry(tmp / "b" / "documents.json")
            repo = JsonDocumentRepository(registry)
            vector_store = VectorStore(DIMENSION)
            metadata_store = MetadataStore()
            faiss_path = tmp / "b" / "faiss" / "index.faiss"
            metadata_path = tmp / "b" / "metadata.json"
            _seed_existing(vector_store, metadata_store, faiss_path, metadata_path, registry)
            before = _state(vector_store, metadata_store, faiss_path, metadata_path, repo)
            service = _build_service(
                StubPDFProcessor(fail=True), metadata_store, vector_store, tmp / "b"
            )
            user = auth.register("b@example.com", PASSWORD)
            token = _access_token(user)
            with _overrides(auth, repo, service) as client:
                resp = _upload(client, token)
                check(
                    "B. indexing failure returns 400",
                    resp.status_code == 400,
                    f"status={resp.status_code}",
                )
            _check_restored(check, "B.", before, _state(vector_store, metadata_store, faiss_path, metadata_path, repo))

        # C. Metadata persistence failure.
        with _storage(tmp / "c"):
            auth = _make_auth(tmp / "c")
            registry = DocumentRegistry(tmp / "c" / "documents.json")
            repo = JsonDocumentRepository(registry)
            vector_store = VectorStore(DIMENSION)
            metadata_store = FailingMetadataStore()
            faiss_path = tmp / "c" / "faiss" / "index.faiss"
            metadata_path = tmp / "c" / "metadata.json"
            _seed_existing(vector_store, metadata_store, faiss_path, metadata_path, registry)
            before = _state(vector_store, metadata_store, faiss_path, metadata_path, repo)
            service = _build_service(
                StubPDFProcessor(), metadata_store, vector_store, tmp / "c"
            )
            user = auth.register("c@example.com", PASSWORD)
            token = _access_token(user)
            with _overrides(auth, repo, service) as client:
                resp = _upload(client, token)
                check(
                    "C. metadata persistence failure returns 400",
                    resp.status_code == 400,
                    f"status={resp.status_code}",
                )
            _check_restored(check, "C.", before, _state(vector_store, metadata_store, faiss_path, metadata_path, repo))

        # D. Registry failure.
        with _storage(tmp / "d"):
            auth = _make_auth(tmp / "d")
            registry = DocumentRegistry(tmp / "d" / "documents.json")
            repo = RaisingRegisterRepository(registry)
            vector_store = VectorStore(DIMENSION)
            metadata_store = MetadataStore()
            faiss_path = tmp / "d" / "faiss" / "index.faiss"
            metadata_path = tmp / "d" / "metadata.json"
            _seed_existing(vector_store, metadata_store, faiss_path, metadata_path, registry)
            before = _state(vector_store, metadata_store, faiss_path, metadata_path, repo)
            service = _build_service(
                StubPDFProcessor(), metadata_store, vector_store, tmp / "d"
            )
            user = auth.register("d@example.com", PASSWORD)
            token = _access_token(user)
            with _overrides(auth, repo, service) as client:
                resp = _upload(client, token)
                check(
                    "D. registry failure returns 500",
                    resp.status_code == 500,
                    f"status={resp.status_code}",
                )
            _check_restored(check, "D.", before, _state(vector_store, metadata_store, faiss_path, metadata_path, repo))

        # E. Existing document survives a failed second upload.
        with _storage(tmp / "e"):
            auth = _make_auth(tmp / "e")
            registry = DocumentRegistry(tmp / "e" / "documents.json")
            repo = JsonDocumentRepository(registry)
            vector_store = VectorStore(DIMENSION)
            metadata_store = MetadataStore()
            faiss_path = tmp / "e" / "faiss" / "index.faiss"
            metadata_path = tmp / "e" / "metadata.json"
            _seed_existing(vector_store, metadata_store, faiss_path, metadata_path, registry)
            service = _build_service(
                StubPDFProcessor(fail=True), metadata_store, vector_store, tmp / "e"
            )
            user = auth.register("e@example.com", PASSWORD)
            token = _access_token(user)
            with _overrides(auth, repo, service) as client:
                _upload(client, token)
            check(
                "E. existing document still registered",
                _registry_ids(repo) == ["doc-existing"],
                str(_registry_ids(repo)),
            )
            check(
                "E. existing chunk still in metadata",
                any(
                    record["document_id"] == "doc-existing"
                    and record["text"] == "existing chunk"
                    for record in metadata_store.get_all_documents()
                ),
            )
            _, indices = vector_store.search([0.1] * DIMENSION, 1)
            check(
                "E. existing vector still present in FAISS",
                vector_store.ntotal == 1 and indices[0][0] == 0,
                f"ntotal={vector_store.ntotal}",
            )

        # F. Cleanup failure never replaces the original exception.
        with _storage(tmp / "f"):
            auth = _make_auth(tmp / "f")
            registry = DocumentRegistry(tmp / "f" / "documents.json")
            repo = JsonDocumentRepository(registry)
            vector_store = VectorStore(DIMENSION)
            metadata_store = MetadataStore()
            faiss_path = tmp / "f" / "faiss" / "index.faiss"
            metadata_path = tmp / "f" / "metadata.json"
            _seed_existing(vector_store, metadata_store, faiss_path, metadata_path, registry)
            before = _state(vector_store, metadata_store, faiss_path, metadata_path, repo)
            service = _build_service(
                StubPDFProcessor(fail=True), metadata_store, vector_store, tmp / "f"
            )
            user = auth.register("f@example.com", PASSWORD)
            token = _access_token(user)
            with mock.patch.object(Path, "unlink", side_effect=OSError("file locked")):
                with _overrides(auth, repo, service) as client:
                    resp = _upload(client, token)
            check(
                "F. original exception preserved despite cleanup failure",
                resp.status_code == 400
                and "could not be indexed" in resp.json()["error"]["message"],
                f"status={resp.status_code}",
            )
            body_text = str(resp.json())
            check(
                "F. internal exception details are not exposed",
                "simulated extraction failure" not in body_text
                and "file locked" not in body_text,
            )
            after = _state(vector_store, metadata_store, faiss_path, metadata_path, repo)
            check(
                "F. state still restored despite cleanup failure",
                after["faiss_disk"] == before["faiss_disk"]
                and after["meta_disk"] == before["meta_disk"]
                and after["registry"] == before["registry"],
            )
            check(
                "F. failed cleanup left the pdf in place",
                len(_pdf_files()) == 1,
                f"pdfs={len(_pdf_files())}",
            )

        # G. Consistency checker reports the same state before and after.
        with _storage(tmp / "g"):
            auth = _make_auth(tmp / "g")
            registry = DocumentRegistry(tmp / "g" / "documents.json")
            repo = JsonDocumentRepository(registry)
            vector_store = VectorStore(DIMENSION)
            metadata_store = MetadataStore()
            faiss_path = tmp / "g" / "faiss" / "index.faiss"
            metadata_path = tmp / "g" / "metadata.json"
            _seed_existing(vector_store, metadata_store, faiss_path, metadata_path, registry)
            before_report = check_consistency(vector_store, metadata_store, repo)
            service = _build_service(
                StubPDFProcessor(fail=True), metadata_store, vector_store, tmp / "g"
            )
            user = auth.register("g@example.com", PASSWORD)
            token = _access_token(user)
            with _overrides(auth, repo, service) as client:
                _upload(client, token)
            after_report = check_consistency(vector_store, metadata_store, repo)
            check(
                "G. consistency counts identical before and after",
                before_report.vector_count == after_report.vector_count == 1
                and before_report.metadata_count == after_report.metadata_count == 1,
                f"before=({before_report.vector_count},{before_report.metadata_count}) "
                f"after=({after_report.vector_count},{after_report.metadata_count})",
            )
            check(
                "G. healthy before and after failed upload",
                before_report.healthy and after_report.healthy,
            )

        # H. SQLite-backed PostgreSQL repository code path.
        with _storage(tmp / "h"):
            engine = create_engine(f"sqlite:///{(tmp / 'h' / 'pg.db').as_posix()}")
            Base.metadata.create_all(engine)
            session_factory = sessionmaker(bind=engine, expire_on_commit=False)
            repo = PostgresDocumentRepository(session_factory)
            auth = _make_auth(tmp / "h")
            vector_store = VectorStore(DIMENSION)
            metadata_store = MetadataStore()
            faiss_path = tmp / "h" / "faiss" / "index.faiss"
            metadata_path = tmp / "h" / "metadata.json"
            service = _build_service(
                StubPDFProcessor(), metadata_store, vector_store, tmp / "h"
            )
            user = auth.register("h@example.com", PASSWORD)
            token = _access_token(user)
            with _overrides(auth, repo, service) as client:
                resp = _upload(client, token)
                check(
                    "H. success works through the repository abstraction",
                    resp.status_code == 200
                    and len(repo.list_all_documents()) == 1,
                    f"status={resp.status_code}",
                )
            before = _state(vector_store, metadata_store, faiss_path, metadata_path, repo)
            service_fail = _build_service(
                StubPDFProcessor(fail=True), metadata_store, vector_store, tmp / "h"
            )
            with _overrides(auth, repo, service_fail) as client:
                resp = _upload(client, token, "second.pdf")
                check(
                    "H. failure rolls back through the repository abstraction",
                    resp.status_code == 400
                    and len(repo.list_all_documents()) == 1,
                    f"status={resp.status_code} docs={len(repo.list_all_documents())}",
                )
            _check_restored(check, "H.", before, _state(vector_store, metadata_store, faiss_path, metadata_path, repo))
            engine.dispose()

    print("\n" + "=" * 60)
    print("Upload Failure Compensation Test " + ("PASSED" if not checks["failed"] else "FAILED"))
    print("=" * 60)
    return 1 if checks["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())