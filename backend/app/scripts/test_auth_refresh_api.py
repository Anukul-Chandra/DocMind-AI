"""Auth refresh API integration tests.

Exercises POST /auth/refresh through the real FastAPI app with the
``get_auth_service`` dependency overridden to a dedicated AuthService bound to
an isolated JSON user repository. Verifies:

    1. a valid refresh token returns a fresh access/refresh token pair
    2. an invalid token is rejected with 401
    3. an expired token is rejected with 401
    4. an access token cannot be used as a refresh token
    5. the refreshed access token is accepted by an auth-protected route
    6. missing/blank refresh tokens are rejected by validation (422)

The refresh-token mechanics themselves (claim layout, signature, expiry,
type enforcement) live in the existing JWTService and AuthService; this test
only verifies the endpoint wiring on top of that unchanged logic.

Usage (from backend/):
    python -m app.scripts.test_auth_refresh_api

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

SECRET_PASSWORD = "super-secret-1"
TOKEN_SECRET = "api-test-secret"


def main() -> int:
    """Run all refresh scenarios and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    print("=" * 60)
    print("Auth Refresh API Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        json_repo = JsonUserRepository(Path(tmp) / "users.json")
        auth = AuthService(
            users=json_repo,
            passwords=PasswordService(),
            tokens=JWTService(secret_key=TOKEN_SECRET),
        )
        token_service = JWTService(secret_key=TOKEN_SECRET)
        doc_repo = JsonDocumentRepository(
            DocumentRegistry(Path(tmp) / "documents.json")
        )

        app.dependency_overrides[get_auth_service] = lambda: auth
        app.dependency_overrides[get_document_repository] = lambda: doc_repo

        try:
            with TestClient(app) as client:
                user = auth.register("refresh@example.com", SECRET_PASSWORD)
                login = client.post(
                    "/auth/login",
                    json={
                        "email": "refresh@example.com",
                        "password": SECRET_PASSWORD,
                    },
                ).json()["data"]
                access_token = login["access_token"]
                refresh_token = login["refresh_token"]

                # 1. Valid refresh token returns a fresh pair.
                response = client.post(
                    "/auth/refresh",
                    json={"refresh_token": refresh_token},
                )
                body = response.json()
                data = body.get("data", {})
                new_access = data.get("access_token")
                new_refresh = data.get("refresh_token")
                check(
                    "1. valid refresh token returns 200",
                    response.status_code == 200 and body.get("success") is True,
                )
                check(
                    "1. response is a token pair",
                    bool(new_access)
                    and bool(new_refresh)
                    and data.get("token_type") == "bearer",
                )
                check(
                    "1. new access token differs from the original",
                    new_access != access_token,
                )
                check(
                    "1. new access token verifies with the right subject",
                    token_service.verify_token(new_access, "access") == user.user_id,
                )
                check(
                    "1. new refresh token verifies as a refresh token",
                    token_service.verify_token(new_refresh, "refresh") == user.user_id,
                )
                check(
                    "1. response exposes no password material",
                    "password" not in str(body)
                    and "password_hash" not in str(body),
                )

                # 5. The refreshed access token is accepted by a protected route.
                protected = client.get(
                    "/documents",
                    headers={"Authorization": f"Bearer {new_access}"},
                )
                check(
                    "5. refreshed access token works on a protected route",
                    protected.status_code == 200,
                    f"status={protected.status_code}",
                )

                # 4. An access token cannot be redeemed as a refresh token.
                response = client.post(
                    "/auth/refresh",
                    json={"refresh_token": access_token},
                )
                body = response.json()
                check(
                    "4. access token rejected as refresh token",
                    response.status_code == 401
                    and body.get("success") is False
                    and body.get("error", {}).get("code") == "unauthorized",
                    f"status={response.status_code}",
                )

                # 2. Invalid/malformed token is rejected.
                response = client.post(
                    "/auth/refresh",
                    json={"refresh_token": "not.a.jwt"},
                )
                body = response.json()
                check(
                    "2. malformed token rejected with 401",
                    response.status_code == 401
                    and body.get("success") is False
                    and body.get("error", {}).get("code") == "unauthorized",
                )

                # 2. A well-formed token signed by another secret is rejected.
                foreign = JWTService(secret_key="different-secret").create_refresh_token(
                    user.user_id
                )
                response = client.post(
                    "/auth/refresh",
                    json={"refresh_token": foreign},
                )
                check(
                    "2. foreign-signature token rejected with 401",
                    response.status_code == 401,
                    f"status={response.status_code}",
                )

                # 3. An expired refresh token is rejected.
                expired = token_service.create_refresh_token(
                    user.user_id, expires_in=-1
                )
                response = client.post(
                    "/auth/refresh",
                    json={"refresh_token": expired},
                )
                body = response.json()
                check(
                    "3. expired refresh token rejected with 401",
                    response.status_code == 401
                    and body.get("success") is False
                    and body.get("error", {}).get("code") == "unauthorized",
                    f"status={response.status_code}",
                )

                # 3. A token for a now-missing user is rejected.
                orphan = token_service.create_refresh_token("no-such-user")
                response = client.post(
                    "/auth/refresh",
                    json={"refresh_token": orphan},
                )
                check(
                    "3. token for missing user rejected with 401",
                    response.status_code == 401,
                    f"status={response.status_code}",
                )

                # 6. Missing / blank refresh tokens fail validation.
                response = client.post("/auth/refresh", json={})
                check(
                    "6. missing refresh token rejected with 422",
                    response.status_code == 422
                    and response.json().get("error", {}).get("code")
                    == "validation_error",
                )
                response = client.post(
                    "/auth/refresh", json={"refresh_token": "   "}
                )
                body = response.json()
                check(
                    "6. blank refresh token rejected as invalid",
                    response.status_code == 401
                    and body.get("error", {}).get("code") == "unauthorized",
                    f"status={response.status_code}",
                )

                # 1. A refresh token can be redeemed repeatedly for fresh pairs.
                second = client.post(
                    "/auth/refresh",
                    json={"refresh_token": new_refresh},
                )
                second_access = second.json().get("data", {}).get("access_token")
                check(
                    "1. refreshed token can be redeemed again",
                    second.status_code == 200
                    and bool(second_access)
                    and second_access != new_access,
                )
        finally:
            app.dependency_overrides.clear()

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(f"Auth Refresh API Test {'PASSED' if all_passed else 'FAILED'}")
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())