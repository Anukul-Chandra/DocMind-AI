"""Focused tests for the get_current_user authentication dependency.

Exercises the dependency through a dedicated FastAPI test app whose /me route
is guarded by get_current_user, over both the JSON and PostgreSQL user
repositories. Verifies Bearer parsing, token verification, access-token-type
enforcement, expiry, unknown and inactive user rejection, the standardized 401
envelope, and that the resolved object is the domain User model (not a
database model).

Usage (from backend/):
    python -m app.scripts.test_auth_dependency

Requires PostgreSQL to be reachable (see .env DATABASE_URL) for the Postgres
scenario. Exit status is non-zero if any check fails.
"""

import json
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.dependencies import get_auth_service, get_current_user
from app.api.errors import register_exception_handlers
from app.db.session import get_session_factory
from app.repositories.json.user_repository import JsonUserRepository
from app.repositories.postgres.user_repository import PostgresUserRepository
from app.services.auth import AuthService, JWTService, PasswordService, User

SECRET_PASSWORD = "super-secret-1"
TOKEN_SECRET = "api-test-secret"

_captured_users: list[User] = []


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
        tokens=JWTService(secret_key=TOKEN_SECRET),
    )


def build_test_app(service: AuthService) -> FastAPI:
    """Build a FastAPI app exposing /me guarded by get_current_user.

    The resolved user is recorded so tests can inspect the returned object.
    The AuthService dependency is overridden on the test app so the real
    (configured) service is never invoked.

    Args:
        service: The AuthService to inject.

    Returns:
        A configured test app.
    """

    def me(current_user: User = Depends(get_current_user)) -> dict:
        _captured_users.append(current_user)
        return {"user_id": current_user.user_id, "email": current_user.email}

    test_app = FastAPI()
    register_exception_handlers(test_app)
    test_app.dependency_overrides[get_auth_service] = lambda: service
    test_app.get("/me")(me)
    return test_app


def auth_header(value: str) -> dict[str, str]:
    """Build an Authorization header dict.

    Args:
        value: The raw header value.

    Returns:
        A one-entry header dict.
    """
    return {"Authorization": value}


def main() -> int:
    """Run all dependency scenarios."""
    print("=" * 60)
    print("Auth Dependency (get_current_user) Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        json_repo = JsonUserRepository(Path(tmp) / "users.json")
        service = build_auth_service(json_repo)
        tokens = JWTService(secret_key=TOKEN_SECRET)

        created = json_repo.create(
            email="dep.json@example.com",
            password_hash=PasswordService().hash(SECRET_PASSWORD),
        )
        inactive = json_repo.create(
            email="dep.inactive@example.com",
            password_hash=PasswordService().hash(SECRET_PASSWORD),
            is_active=False,
        )

        _captured_users.clear()
        with TestClient(build_test_app(service)) as client:
            # A. Valid access token returns the current user.
            access = tokens.create_access_token(created.user_id)
            response = client.get("/me", headers=auth_header(f"Bearer {access}"))
            check(
                "A. valid access token returns the user",
                response.status_code == 200
                and response.json().get("user_id") == created.user_id,
            )

            # K. The returned object is the domain User, not a database model.
            check(
                "K. dependency returns the domain User",
                len(_captured_users) == 1
                and isinstance(_captured_users[-1], User)
                and not hasattr(_captured_users[-1], "__table__"),
            )

            failure_bodies: list[tuple[int, object]] = []

            def record_failure(name: str, response) -> None:
                failure_bodies.append((response.status_code, response.json()))
                check(name, response.status_code == 401)

            # B. Missing Authorization header → 401.
            record_failure("B. missing header returns 401", client.get("/me"))

            # C. Invalid Bearer token → 401.
            record_failure(
                "C. invalid bearer token returns 401",
                client.get("/me", headers=auth_header("Bearer not.a.jwt")),
            )

            # D. Malformed Authorization headers → 401.
            malformed_headers = [
                "Bearer",
                "Bearer token extra",
                "Basic abcdef",
                "bearer token",
            ]
            for header in malformed_headers:
                response = client.get("/me", headers=auth_header(header))
                if response.status_code != 401:
                    check("D. malformed header returns 401", False, repr(header))
                    break
            else:
                check("D. malformed header returns 401", True)

            # E. Refresh token supplied as a Bearer access token → 401.
            refresh = tokens.create_refresh_token(created.user_id)
            record_failure(
                "E. refresh token as access token returns 401",
                client.get("/me", headers=auth_header(f"Bearer {refresh}")),
            )

            # F. Expired access token → 401.
            expired = tokens.create_access_token(created.user_id, expires_in=-1)
            record_failure(
                "F. expired access token returns 401",
                client.get("/me", headers=auth_header(f"Bearer {expired}")),
            )

            # G. Token for a nonexistent/deleted user → 401.
            ghost = tokens.create_access_token("no-such-user-id")
            record_failure(
                "G. token for deleted user returns 401",
                client.get("/me", headers=auth_header(f"Bearer {ghost}")),
            )

            # H. Token for an inactive user → 401.
            inactive_access = tokens.create_access_token(inactive.user_id)
            record_failure(
                "H. token for inactive user returns 401",
                client.get("/me", headers=auth_header(f"Bearer {inactive_access}")),
            )

            # All 401 responses are the same generic envelope (no cause leak).
            check(
                "5. all failures share one generic 401 response",
                len(failure_bodies) == 6
                and all(code == 401 for code, _ in failure_bodies)
                and len({json.dumps(body, sort_keys=True) for _, body in failure_bodies})
                == 1,
            )

        # PostgreSQL persistence scenario.
        pg_repo = PostgresUserRepository(get_session_factory())
        pg_service = build_auth_service(pg_repo)
        pg_email = f"dep.pg.{uuid.uuid4().hex}@example.com"
        try:
            pg_user = pg_repo.create(
                email=pg_email,
                password_hash=PasswordService().hash(SECRET_PASSWORD),
            )
            _captured_users.clear()
            with TestClient(build_test_app(pg_service)) as client:
                # J. Valid access token over PostgreSQL returns the user.
                pg_access = tokens.create_access_token(pg_user.user_id)
                response = client.get(
                    "/me", headers=auth_header(f"Bearer {pg_access}")
                )
                check(
                    "J. PostgreSQL valid token returns the user",
                    response.status_code == 200
                    and response.json().get("user_id") == pg_user.user_id,
                )
                # K (postgres). The returned object is the domain User.
                check(
                    "K. PostgreSQL returns the domain User",
                    len(_captured_users) == 1
                    and isinstance(_captured_users[-1], User)
                    and not hasattr(_captured_users[-1], "__table__"),
                )
                # Refresh token is rejected on the Postgres backend too.
                pg_refresh = tokens.create_refresh_token(pg_user.user_id)
                response = client.get(
                    "/me", headers=auth_header(f"Bearer {pg_refresh}")
                )
                check(
                    "E. PostgreSQL refresh token rejected",
                    response.status_code == 401,
                )
        finally:
            with get_session_factory()() as session:
                session.execute(
                    text("DELETE FROM users WHERE email = :email"),
                    {"email": pg_email},
                )
                session.commit()

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(f"Auth Dependency Test {'PASSED' if all_passed else 'FAILED'}")
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())