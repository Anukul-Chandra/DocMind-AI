"""Registration API integration tests (JSON and PostgreSQL persistence).

Exercises POST /auth/register through the real FastAPI app with the
``get_auth_service`` dependency overridden to a dedicated AuthService bound to
either the JSON user repository (isolated temp file) or the PostgreSQL
repository. Verifies success paths, duplicate handling, email normalization,
password hashing, response safety, active state, and the standardized error
envelope.

Usage (from backend/):
    python -m app.scripts.test_auth_api

Requires PostgreSQL to be reachable (see .env DATABASE_URL) for the Postgres
scenario. Exit status is non-zero if any check fails.
"""

import sys
import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.dependencies import get_auth_service
from app.db.session import get_session_factory
from app.main import app
from app.repositories.json.user_repository import JsonUserRepository
from app.repositories.postgres.user_repository import PostgresUserRepository
from app.services.auth import AuthService, JWTService, PasswordService

SECRET_PASSWORD = "super-secret-1"


def build_auth_service(users) -> AuthService:
    """Build an AuthService bound to the given user repository.

    Args:
        users: A UserRepository implementation.

    Returns:
        A fully wired AuthService.
    """
    return AuthService(
        users=users,
        passwords=PasswordService(),
        tokens=JWTService(secret_key="api-test-secret"),
    )


def register(client: TestClient, email: str, password: str):
    """POST /auth/register and return the response.

    Args:
        client: The API test client.
        email: The email to register.
        password: The password to register.

    Returns:
        The FastAPI test response.
    """
    return client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )


def main() -> int:
    """Run all registration scenarios."""
    print("=" * 60)
    print("Registration API Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        json_repo = JsonUserRepository(Path(tmp) / "users.json")
        app.dependency_overrides[get_auth_service] = lambda: build_auth_service(
            json_repo
        )

        with TestClient(app) as client:
            # A. Successful registration with JSON persistence.
            response = register(client, "alice@example.com", SECRET_PASSWORD)
            body = response.json()
            check(
                "A. JSON registration returns 201",
                response.status_code == 201 and body.get("success") is True,
            )
            data = body.get("data", {})
            check(
                "A. JSON registration returns the user",
                data.get("email") == "alice@example.com"
                and data.get("is_active") is True
                and bool(data.get("user_id")),
            )

            # F. Response never exposes password material.
            serialized = str(body)
            check(
                "F. response contains no password fields",
                "password" not in serialized and "password_hash" not in serialized,
            )

            # E. Password is stored only as a hash.
            stored = json_repo.get_by_email("alice@example.com")
            stored_hash = stored.password_hash if stored else ""
            check(
                "E. stored hash differs from plaintext",
                bool(stored_hash) and stored_hash != SECRET_PASSWORD,
            )
            check(
                "E. stored hash verifies the password",
                PasswordService().verify(SECRET_PASSWORD, stored_hash),
            )

            # G. New user is_active is True in storage.
            check(
                "G. new user is_active True",
                stored is not None and stored.is_active is True,
            )

            # C. Duplicate email returns 409 with the standard envelope.
            response = register(client, "alice@example.com", SECRET_PASSWORD)
            body = response.json()
            check(
                "C. duplicate email returns 409 conflict",
                response.status_code == 409
                and body.get("success") is False
                and body.get("error", {}).get("code") == "conflict",
            )

            # D. Email normalization: mixed case then lowercase are duplicates.
            response = register(client, "User@example.com", SECRET_PASSWORD)
            body = response.json()
            check(
                "D. mixed-case email registration succeeds",
                response.status_code == 201
                and body.get("data", {}).get("email") == "user@example.com",
            )
            response = register(client, "user@example.com", SECRET_PASSWORD)
            check(
                "D. case-variant email rejected as duplicate",
                response.status_code == 409,
            )

            # H. Invalid input returns the standard validation response.
            response = register(client, "bob@example.com", "short")
            body = response.json()
            check(
                "H. short password rejected with validation envelope",
                response.status_code == 422
                and body.get("success") is False
                and body.get("error", {}).get("code") == "validation_error",
            )
            response = register(client, "not-an-email", SECRET_PASSWORD)
            body = response.json()
            check(
                "H. malformed email rejected with validation envelope",
                response.status_code == 422
                and body.get("success") is False
                and body.get("error", {}).get("code") == "validation_error",
            )

        # PostgreSQL persistence scenario.
        pg_repo = PostgresUserRepository(get_session_factory())
        app.dependency_overrides[get_auth_service] = lambda: build_auth_service(
            pg_repo
        )
        pg_email = f"pg.{uuid.uuid4().hex}@example.com"
        try:
            with TestClient(app) as client:
                # B. Successful registration with PostgreSQL persistence.
                response = register(client, pg_email, SECRET_PASSWORD)
                body = response.json()
                data = body.get("data", {})
                check(
                    "B. PostgreSQL registration returns 201",
                    response.status_code == 201
                    and body.get("success") is True
                    and data.get("email") == pg_email
                    and data.get("is_active") is True
                    and bool(data.get("user_id")),
                )
                check(
                    "F. PostgreSQL response has no password fields",
                    "password" not in str(body)
                    and "password_hash" not in str(body),
                )
                pg_stored = pg_repo.get_by_email(pg_email)
                check(
                    "E. PostgreSQL stores only the hash",
                    pg_stored is not None
                    and pg_stored.password_hash != SECRET_PASSWORD
                    and PasswordService().verify(SECRET_PASSWORD, pg_stored.password_hash),
                )

                # C (postgres). Duplicate email is a 409.
                response = register(client, pg_email, SECRET_PASSWORD)
                body = response.json()
                check(
                    "C. PostgreSQL duplicate email returns 409 conflict",
                    response.status_code == 409
                    and body.get("error", {}).get("code") == "conflict",
                )
        finally:
            app.dependency_overrides.clear()
            with get_session_factory()() as session:
                session.execute(
                    text("DELETE FROM users WHERE email = :email"),
                    {"email": pg_email},
                )
                session.commit()

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(f"Registration API Test {'PASSED' if all_passed else 'FAILED'}")
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())