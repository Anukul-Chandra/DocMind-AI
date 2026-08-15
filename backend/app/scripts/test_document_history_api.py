"""Focused API verification of document history listing and ownership isolation.

Exercises the real ``GET /documents`` route against an isolated JSON-backed
registry seeded with documents owned by two users, verifying:

    1. an authenticated user sees their own document history
    2. documents belonging to another user are never returned
    3. the classification field is present for every document so the frontend
       type filter has data
    4. deleted-but-owned documents still appear in the owner's history

The client-side filename search and classification filter live in the frontend
(``src/lib/document-filter.ts``) and are covered by
``frontend/scripts/test-document-filter.mts``.

Usage (from backend/):
    python -m app.scripts.test_document_history_api

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_document_repository
from app.main import app
from app.repositories.json.document_repository import JsonDocumentRepository
from app.repositories.json.user_repository import JsonUserRepository
from app.services.auth import AuthService, JWTService, PasswordService
from app.services.document_registry import DocumentRegistry

PASSWORD = "super-secret-1"
TOKEN_SECRET = "test-token-secret"


def main() -> int:
    """Run all document history checks and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    print("=" * 40)
    print("Document History API Verification")
    print("=" * 40)
    print()

    results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "PASS" if passed else "FAIL"
        print(f"{name:<58}{status}")
        if not passed and detail:
            print(f"  {detail}")
        results.append(passed)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        user_repo = JsonUserRepository(tmp / "users.json")
        auth = AuthService(
            users=user_repo,
            passwords=PasswordService(),
            tokens=JWTService(secret_key=TOKEN_SECRET),
        )
        user_a = auth.register("alice@example.com", PASSWORD)
        user_b = auth.register("bob@example.com", PASSWORD)
        token_service = JWTService(secret_key=TOKEN_SECRET)
        token_a = token_service.create_access_token(user_a.user_id)
        token_b = token_service.create_access_token(user_b.user_id)

        registry = DocumentRegistry(tmp / "documents.json")
        repo = JsonDocumentRepository(registry)
        repo.register("default", "invoice-report.pdf", 4, user_a.user_id, "a1", "invoice")
        repo.register("default", "resume.pdf", 2, user_a.user_id, "a2", "resume")
        repo.register("default", "old.pdf", 1, user_a.user_id, "a3", "unknown")
        registry.delete_document("a3", user_a.user_id)
        repo.register("default", "secret-invoice.pdf", 3, user_b.user_id, "b1", "invoice")

        app.dependency_overrides[get_auth_service] = lambda: auth
        app.dependency_overrides[get_document_repository] = lambda: repo

        try:
            with TestClient(app) as client:
                check(
                    "A. unauthenticated request rejected",
                    client.get("/documents").status_code == 401,
                )

                resp_a = client.get(
                    "/documents",
                    headers={"Authorization": f"Bearer {token_a}"},
                )
                body_a = resp_a.json()
                data_a = body_a.get("data", [])
                ids_a = {document["document_id"] for document in data_a}
                by_id_a = {document["document_id"]: document for document in data_a}
                check(
                    "A. authenticated user sees their document history",
                    resp_a.status_code == 200
                    and body_a.get("success") is True
                    and {"a1", "a2", "a3"} <= ids_a,
                    f"status={resp_a.status_code}, ids={sorted(ids_a)}",
                )
                check(
                    "A. deleted-but-owned document still in history",
                    "a3" in ids_a,
                )
                check(
                    "B. another user's documents are never returned",
                    resp_a.status_code == 200 and "b1" not in ids_a,
                    f"ids={sorted(ids_a)}",
                )
                check(
                    "C. classification present for every listed document",
                    all(
                        isinstance(document.get("classification"), str)
                        and document["classification"]
                        for document in data_a
                    )
                    and by_id_a["a1"]["classification"] == "invoice"
                    and by_id_a["a2"]["classification"] == "resume",
                )
                check(
                    "C. deleted document reports unknown type",
                    by_id_a["a3"]["classification"] == "unknown",
                    f"got {by_id_a['a3'].get('classification')}",
                )

                resp_b = client.get(
                    "/documents",
                    headers={"Authorization": f"Bearer {token_b}"},
                )
                data_b = resp_b.json().get("data", [])
                ids_b = {document["document_id"] for document in data_b}
                check(
                    "B. user B sees only their own history",
                    resp_b.status_code == 200 and ids_b == {"b1"},
                    f"ids={sorted(ids_b)}",
                )
                check(
                    "B. user A's documents never leak to user B",
                    "a1" not in ids_b and "a2" not in ids_b,
                )
        finally:
            app.dependency_overrides.clear()

    print()
    print("=" * 40)
    overall = all(results)
    print("PASS" if overall else "FAIL")
    print("=" * 40)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())