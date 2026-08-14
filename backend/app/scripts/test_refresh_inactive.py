"""Focused regression test for inactive-user refresh-token rejection.

An inactive account must not be able to redeem a valid refresh token: the
refresh attempt is rejected with the same generic ``InvalidCredentialsError``
used for invalid/expired tokens, no new token pair is issued, and the failure
does not reveal that the account is inactive. An active user's refresh must
continue to work.

Usage (from backend/):
    python -m app.scripts.test_refresh_inactive

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
from app.services.storage import JsonFileStore

EMAIL = "refresh.inactive@example.com"
PASSWORD = "s3cret-password"


def deactivate_user(repo: JsonUserRepository, user_id: str, path: Path) -> None:
    """Mark a stored user record inactive and reload it into the repository.

    Mirrors how an account would be disabled at the storage layer: the record's
    ``is_active`` flag is flipped in the JSON file and the same repository
    instance (still held by AuthService) is reloaded from disk.

    Args:
        repo: The repository instance backing the AuthService under test.
        user_id: The id of the user to deactivate.
        path: The JSON storage file path.
    """
    records = JsonFileStore.load(path, default=[])
    for record in records:
        if record["id"] == user_id:
            record["is_active"] = False
    JsonFileStore.save(path, records)
    repo._load()


def main() -> int:
    """Run the inactive-user refresh regression scenarios."""
    print("=" * 60)
    print("Inactive-User Refresh Rejection Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "users.json"
        repository = JsonUserRepository(path)
        passwords = PasswordService()
        tokens = JWTService(secret_key="test-secret-key")
        auth = AuthService(users=repository, passwords=passwords, tokens=tokens)

        user = auth.register(EMAIL, PASSWORD)
        pair = auth.authenticate(EMAIL, PASSWORD)

        # An active user's refresh must still work and issue a new pair.
        try:
            refreshed = auth.refresh(pair.refresh_token)
            refreshed_access_ok = (
                tokens.verify_token(refreshed.access_token, "access") == user.user_id
            )
            refreshed_refresh_ok = (
                tokens.verify_token(refreshed.refresh_token, "refresh") == user.user_id
            )
            check(
                "active user refresh issues a new pair",
                bool(refreshed.access_token)
                and bool(refreshed.refresh_token)
                and refreshed_access_ok
                and refreshed_refresh_ok,
            )
        except InvalidCredentialsError as exc:
            check("active user refresh issues a new pair", False, str(exc))

        # Deactivate the user; the previously issued refresh token must now fail.
        deactivate_user(repository, user.user_id, path)
        try:
            auth.refresh(pair.refresh_token)
            check("inactive user refresh is rejected", False, "no error raised")
        except InvalidCredentialsError as exc:
            check("inactive user refresh is rejected", True)
            # The failure must not reveal that the account is inactive.
            check(
                "inactive-user failure is generic",
                "inactive" not in str(exc).lower(),
                str(exc),
            )

        # No new token pair may have been issued: the access token issued
        # before deactivation is still bound to the (now inactive) user, and
        # get_user_from_access_token must reject it.
        try:
            auth.get_user_from_access_token(pair.access_token)
            check("no new access token usable after deactivation", False)
        except InvalidCredentialsError:
            check("no new access token usable after deactivation", True)

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(
        f"Inactive-User Refresh Test {'PASSED' if all_passed else 'FAILED'}"
    )
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
