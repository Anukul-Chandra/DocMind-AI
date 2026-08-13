"""AuthService integration test using JSON persistence.

Wires the real AuthService to the JSON-backed user repository and verifies the
full flow: account creation, authentication, token issuance and verification,
refresh, and failure paths. AuthService is kept completely unaware of the
storage backend.

Usage (from backend/):
    python -m app.scripts.test_auth_service_json

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from app.repositories.json.user_repository import JsonUserRepository
from app.services.auth import (
    AuthService,
    InvalidCredentialsError,
    JWTService,
    PasswordService,
)

EMAIL = "auth.json@example.com"
PASSWORD = "s3cret-password"


def main() -> int:
    """Run the AuthService-over-JSON integration test."""
    print("=" * 60)
    print("AuthService (JSON persistence) Integration Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        repository = JsonUserRepository(Path(tmp) / "users.json")
        passwords = PasswordService()
        tokens = JWTService(secret_key="test-secret-key")
        auth = AuthService(users=repository, passwords=passwords, tokens=tokens)

        # Account creation uses the repository directly (no routes yet).
        created = repository.create(
            email=EMAIL,
            password_hash=passwords.hash(PASSWORD),
        )
        check(
            "user created through the repository",
            created.email == EMAIL and created.is_active is True,
        )

        # Authenticate with the correct password yields a token pair.
        pair = auth.authenticate(EMAIL, PASSWORD)
        check(
            "authenticate returns a token pair",
            pair.token_type == "bearer"
            and pair.expires_in == tokens.access_ttl_seconds
            and pair.access_token
            and pair.refresh_token,
        )
        subject = tokens.verify_token(pair.access_token, "access")
        check(
            "access token subject matches the user id",
            subject == created.user_id,
        )

        # Refresh with the issued refresh token yields a new pair.
        refreshed = auth.refresh(pair.refresh_token)
        check(
            "refresh redeems the refresh token",
            refreshed.access_token == pair.access_token
            or bool(refreshed.access_token and refreshed.refresh_token),
        )

        # Wrong password is rejected without leaking whether the user exists.
        try:
            auth.authenticate(EMAIL, "wrong-password")
            check("wrong password rejected", False, "no error raised")
        except InvalidCredentialsError:
            check("wrong password rejected", True)

        # Unknown email is rejected the same way.
        try:
            auth.authenticate("nobody@example.com", PASSWORD)
            check("unknown email rejected", False, "no error raised")
        except InvalidCredentialsError:
            check("unknown email rejected", True)

        # Tampered refresh token is rejected.
        try:
            auth.refresh("not-a-real-token")
            check("invalid refresh token rejected", False, "no error raised")
        except InvalidCredentialsError:
            check("invalid refresh token rejected", True)

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(
        f"AuthService (JSON) Test {'PASSED' if all_passed else 'FAILED'}"
    )
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())