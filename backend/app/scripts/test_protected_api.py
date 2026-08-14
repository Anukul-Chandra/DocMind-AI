"""Protection tests for the chat and document APIs.

Exercises the real FastAPI app with the ``get_auth_service``,
``get_document_repository``, ``get_document_service``, and ``get_chat_service``
dependencies overridden so the tests verify authentication and per-user
document ownership wiring without running the embedding or LLM pipeline.

Ownership is enforced by the repository layer, so the scenarios run against
both the JSON-backed registry and the PostgreSQL-backed repository.

Usage (from backend/):
    python -m app.scripts.test_protected_api

Requires PostgreSQL to be reachable (see .env DATABASE_URL) for the Postgres
scenario. Exit status is non-zero if any check fails.
"""

import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.dependencies import (
    get_auth_service,
    get_chat_service,
    get_document_repository,
    get_document_service,
    get_retriever,
)
from app.core.config import settings
from app.db.session import get_session_factory
from app.main import app
from app.repositories.json.document_repository import JsonDocumentRepository
from app.repositories.json.user_repository import JsonUserRepository
from app.repositories.postgres.document_repository import PostgresDocumentRepository
from app.repositories.postgres.user_repository import PostgresUserRepository
from app.services.auth import (
    AuthService,
    JWTService,
    PasswordService,
    User,
    UserRepository,
)
from app.services.document import IndexDocumentResult
from app.services.document_registry import DocumentRegistry

SECRET_PASSWORD = "super-secret-1"
TOKEN_SECRET = "api-test-secret"
FAKE_PDF = b"%PDF-1.4\nfake pdf payload for an ownership test\n"


class FakeDocumentService:
    """Stands in for DocumentService so uploads skip the embedding pipeline."""

    def capture_state(self):
        """Return a no-op snapshot (this fake never fails an upload)."""

    def restore_state(self, snapshot) -> None:
        """No-op restore (this fake never mutates shared state)."""

    async def index_document(
        self,
        file_path: str,
        workspace_id: str = "default",
        document_id: str | None = None,
        owner_id: str = "",
        filename: str | None = None,
    ) -> IndexDocumentResult:
        """Return a canned indexing result.

        Args:
            file_path: The uploaded file path.
            workspace_id: The workspace id.
            document_id: The document id.
            owner_id: The user id that owns the document.
            filename: The original uploaded filename.

        Returns:
            A minimal indexing result.
        """
        return IndexDocumentResult(
            filename=filename or Path(file_path).name,
            total_chunks=1,
            total_embeddings=1,
            status="indexed",
        )


class FakeChatService:
    """Stands in for ChatService so /chat skips the LLM pipeline."""

    def __init__(self) -> None:
        self.last_owner_id: str | None = None

    async def chat(self, question: str, owner_id: str = ""):
        """Return a canned chat response and record the owner scope.

        Args:
            question: The user's question.
            owner_id: The owner scope passed through by the API layer.

        Returns:
            A simple namespace with provider, model, and text.
        """
        self.last_owner_id = owner_id
        return SimpleNamespace(provider="fake", model="fake", text="Fake answer.")


class RecordingRetriever:
    """Stands in for the shared Retriever and records retrieval calls."""

    def __init__(self) -> None:
        self.last_owner_id: str | None = None

    def retrieve(self, query: str, k: int = 5, owner_id: str = "") -> list[dict]:
        """Record the owner scope and return no chunks.

        Args:
            query: The search query.
            k: The number of chunks to request.
            owner_id: The owner scope passed by the API layer.

        Returns:
            An empty chunk list.
        """
        self.last_owner_id = owner_id
        return []


def build_auth_service(users: UserRepository) -> AuthService:
    """Build an AuthService bound to the given user repository.

    Args:
        users: A UserRepository implementation.

    Returns:
        A fully wired AuthService.
    """
    return AuthService(
        users=users,
        passwords=PasswordService(),
        tokens=JWTService(secret_key=TOKEN_SECRET),
    )


def register_user(auth: AuthService, email: str) -> User:
    """Register an active user through AuthService.

    Args:
        auth: The AuthService to register with.
        email: The email to register.

    Returns:
        The registered user.
    """
    return auth.register(email, SECRET_PASSWORD)


def bearer(token: str) -> dict[str, str]:
    """Build a Bearer Authorization header.

    Args:
        token: The access token.

    Returns:
        A one-entry header dict.
    """
    return {"Authorization": f"Bearer {token}"}


def upload(client: TestClient, token: str, filename: str = "doc.pdf"):
    """POST /documents/upload with a fake PDF.

    Args:
        client: The API test client.
        token: The access token to authenticate with.
        filename: The uploaded filename.

    Returns:
        The FastAPI test response.
    """
    return client.post(
        "/documents/upload",
        headers=bearer(token),
        files={"file": (filename, FAKE_PDF, "application/pdf")},
    )


def main() -> int:
    """Run all protection scenarios over JSON, then PostgreSQL."""
    print("=" * 60)
    print("Protected API (chat + documents) Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    original_storage_dir = settings.storage_dir
    try:
        _run_json_scenario(check)
        _run_postgres_scenario(check)
    finally:
        settings.storage_dir = original_storage_dir

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(f"Protected API Test {'PASSED' if all_passed else 'FAILED'}")
    print("=" * 60)
    return 0 if all_passed else 1


def _run_json_scenario(check) -> None:
    """Run the JSON persistence scenario.

    Args:
        check: The check-registration callable.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        user_repo = JsonUserRepository(tmp / "users.json")
        doc_repo = JsonDocumentRepository(DocumentRegistry(tmp / "documents.json"))
        auth = build_auth_service(user_repo)
        settings.storage_dir = str(tmp / "uploads")

        client = TestClient(app)
        try:
            _protect_and_own(client, auth, doc_repo, check, label="JSON")
        finally:
            app.dependency_overrides.clear()
            client.close()


def _run_postgres_scenario(check) -> None:
    """Run the PostgreSQL persistence scenario.

    Args:
        check: The check-registration callable.
    """
    user_repo = PostgresUserRepository(get_session_factory())
    doc_repo = PostgresDocumentRepository(get_session_factory())
    auth = build_auth_service(user_repo)
    suffix = uuid.uuid4().hex
    a_email = f"pg.a.{suffix}@example.com"
    b_email = f"pg.b.{suffix}@example.com"
    client = TestClient(app)
    try:
        _protect_and_own(client, auth, doc_repo, check, label="PostgreSQL", a_email=a_email, b_email=b_email)
    finally:
        app.dependency_overrides.clear()
        client.close()
        with get_session_factory()() as session:
            session.execute(
                text(
                    "DELETE FROM documents WHERE owner_id IN "
                    "(SELECT id FROM users WHERE email IN (:a, :b))"
                ),
                {"a": a_email, "b": b_email},
            )
            session.execute(
                text("DELETE FROM users WHERE email IN (:a, :b)"),
                {"a": a_email, "b": b_email},
            )
            session.execute(
                text("DELETE FROM workspaces WHERE id NOT IN (SELECT DISTINCT workspace_id FROM documents)")
            )
            session.commit()


def _protect_and_own(
    client: TestClient,
    auth: AuthService,
    doc_repo,
    check,
    label: str,
    a_email: str = "user.a@example.com",
    b_email: str = "user.b@example.com",
) -> None:
    """Run authentication and ownership checks against a persistence backend.

    Args:
        client: The API test client.
        auth: The AuthService bound to the backend repository.
        doc_repo: The DocumentRepository bound to the backend.
        check: The check-registration callable.
        label: Human-readable backend label for check names.
        a_email: Email for user A.
        b_email: Email for user B.
    """
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_document_repository] = lambda: doc_repo
    app.dependency_overrides[get_document_service] = lambda: FakeDocumentService()
    fake_chat = FakeChatService()
    app.dependency_overrides[get_chat_service] = lambda: fake_chat
    tokens = JWTService(secret_key=TOKEN_SECRET)

    user_a = register_user(auth, a_email)
    user_b = register_user(auth, b_email)
    token_a = tokens.create_access_token(user_a.user_id)
    token_b = tokens.create_access_token(user_b.user_id)

    # A. No token is rejected on chat, retrieve, and document endpoints.
    check(
        f"A. {label} no token -> 401 (documents)",
        client.get("/documents").status_code == 401,
    )
    check(
        f"A. {label} no token -> 401 (chat)",
        client.post("/chat/", json={"question": "hi"}).status_code == 401,
    )
    check(
        f"A. {label} no token -> 401 (retrieve)",
        client.post("/retrieve", json={"query": "hi"}).status_code == 401,
    )

    # B. Invalid token is rejected.
    check(
        f"B. {label} invalid token -> 401 (documents)",
        client.get("/documents", headers=bearer("not.a.jwt")).status_code == 401,
    )
    check(
        f"B. {label} invalid token -> 401 (chat)",
        client.post(
            "/chat/", json={"question": "hi"}, headers=bearer("not.a.jwt")
        ).status_code == 401,
    )
    check(
        f"B. {label} invalid token -> 401 (retrieve)",
        client.post(
            "/retrieve", json={"query": "hi"}, headers=bearer("not.a.jwt")
        ).status_code == 401,
    )

    # C. Valid token reaches the endpoints.
    recording = RecordingRetriever()
    app.dependency_overrides[get_retriever] = lambda: recording
    check(
        f"C. {label} valid token -> documents accessible",
        client.get("/documents", headers=bearer(token_a)).status_code == 200,
    )
    chat_response = client.post(
        "/chat/", json={"question": "hi"}, headers=bearer(token_a)
    )
    check(
        f"C. {label} valid token -> chat accessible",
        chat_response.status_code == 200
        and chat_response.json().get("answer") == "Fake answer.",
    )
    check(
        f"C. {label} chat passes owner id",
        fake_chat.last_owner_id == user_a.user_id,
    )
    retrieve_response = client.post(
        "/retrieve", json={"query": "hi"}, headers=bearer(token_a)
    )
    check(
        f"C. {label} valid token -> retrieve accessible",
        retrieve_response.status_code == 200,
    )
    check(
        f"C. {label} retrieve passes owner id",
        recording.last_owner_id == user_a.user_id,
    )
    app.dependency_overrides.pop(get_retriever)

    # D. User A uploads a document.
    upload_response = upload(client, token_a, filename=f"a-{uuid.uuid4().hex[:8]}.pdf")
    body = upload_response.json()
    check(
        f"D. {label} user A upload returns a document",
        upload_response.status_code == 200
        and body.get("success") is True
        and bool(body.get("data", {}).get("document_id")),
    )
    document_id = body.get("data", {}).get("document_id")

    # K. The document is persisted with user A's ID.
    persisted = doc_repo.get_document(document_id, owner_id=user_a.user_id)
    check(
        f"K. {label} document persisted with user A's id",
        persisted is not None
        and persisted.document_id == document_id
        and persisted.owner_id == user_a.user_id,
    )
    check(
        f"K. {label} document not visible to user B in persistence",
        doc_repo.get_document(document_id, owner_id=user_b.user_id) is None,
    )

    # E. User A can list the document.
    listed = client.get("/documents", headers=bearer(token_a)).json()
    check(
        f"E. {label} user A can list the document",
        any(d.get("document_id") == document_id for d in listed.get("data", [])),
    )

    # F. User A can retrieve it.
    retrieved = client.get(f"/documents/{document_id}", headers=bearer(token_a))
    check(
        f"F. {label} user A can retrieve the document",
        retrieved.status_code == 200
        and retrieved.json().get("data", {}).get("document_id") == document_id,
    )

    # H. User B cannot retrieve user A's document.
    other = client.get(f"/documents/{document_id}", headers=bearer(token_b))
    check(
        f"H. {label} user B cannot retrieve user A's document",
        other.status_code == 404,
    )
    check(
        f"H. {label} user B get does not leak document data",
        "document_id" not in other.json().get("data", {}),
    )

    # J. User B's document list does not contain user A's document.
    b_listed = client.get("/documents", headers=bearer(token_b)).json()
    check(
        f"J. {label} user B list omits user A's document",
        all(d.get("document_id") != document_id for d in b_listed.get("data", [])),
    )

    # I. User B cannot delete user A's document (and it remains intact).
    deleted_by_b = client.delete(
        f"/documents/{document_id}", headers=bearer(token_b)
    )
    check(
        f"I. {label} user B cannot delete user A's document",
        deleted_by_b.status_code == 404,
    )
    after_b_delete = client.get(f"/documents/{document_id}", headers=bearer(token_a))
    check(
        f"I. {label} document intact after user B delete attempt",
        after_b_delete.status_code == 200
        and after_b_delete.json().get("data", {}).get("document_id") == document_id,
    )

    # G. User A can delete the document.
    deleted_by_a = client.delete(f"/documents/{document_id}", headers=bearer(token_a))
    check(
        f"G. {label} user A can delete the document",
        deleted_by_a.status_code == 200
        and deleted_by_a.json().get("data", {}).get("status") == "deleted",
    )
    after_delete = doc_repo.get_document(document_id, owner_id=user_a.user_id)
    check(
        f"G. {label} document soft-deleted in persistence",
        after_delete is not None and after_delete.deleted is True,
    )


if __name__ == "__main__":
    sys.exit(main())