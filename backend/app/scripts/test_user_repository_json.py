"""JSON user repository test.

Verifies the JSON-backed user persistence layer in isolation, including a
reload of a fresh repository instance against the same storage file to prove
records survive across repository lifetimes.

Usage (from backend/):
    python -m app.scripts.test_user_repository_json

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from app.repositories.json.user_repository import JsonUserRepository
from app.services.auth.password import PasswordService

EMAIL = "json.user@example.com"


def main() -> int:
    """Run the JSON user repository test."""
    print("=" * 60)
    print("JSON User Repository Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "users.json"
        repository = JsonUserRepository(path)

        # Creating a user persists it and returns the domain model.
        created = repository.create(
            email=EMAIL,
            password_hash="hash-a",
            user_id="user-1",
        )
        check(
            "create returns the domain user",
            created.user_id == "user-1"
            and created.email == EMAIL
            and created.password_hash == "hash-a"
            and created.is_active is True,
        )
        check(
            "create writes the storage file",
            path.exists(),
        )

        # Retrieving by email.
        found = repository.get_by_email(EMAIL)
        check(
            "find user by email",
            found is not None
            and found.user_id == "user-1"
            and found.email == EMAIL,
        )

        # Retrieving by id.
        found = repository.get_by_id("user-1")
        check(
            "find user by id",
            found is not None and found.email == EMAIL,
        )

        # Unknown users yield None.
        check(
            "unknown email returns None",
            repository.get_by_email("nobody@example.com") is None,
        )
        check(
            "unknown id returns None",
            repository.get_by_id("does-not-exist") is None,
        )

        # Duplicate email rejection.
        try:
            repository.create(email=EMAIL, password_hash="hash-b", user_id="user-2")
            check("duplicate email rejection", False, "no error raised")
        except ValueError:
            check("duplicate email rejection", True)

        # Password hash round-trip: the hash is stored, never the plaintext.
        plaintext = "correct horse battery staple"
        hashed = PasswordService().hash(plaintext)
        repository.create(
            email="hash.json@example.com",
            password_hash=hashed,
            user_id="user-hash",
        )
        stored_hash = repository.get_by_email("hash.json@example.com").password_hash
        check(
            "password_hash round-trip",
            stored_hash == hashed,
        )
        check(
            "plaintext password is never stored",
            stored_hash != plaintext,
        )

        # Inactive state round-trip.
        repository.create(
            email="inactive.json@example.com",
            password_hash="hash-c",
            user_id="user-inactive",
            is_active=False,
        )
        inactive = repository.get_by_id("user-inactive")
        check(
            "is_active round-trip",
            inactive is not None and inactive.is_active is False,
        )

        # Persistence after reloading the repository from the same file.
        reloaded = JsonUserRepository(path)
        check(
            "reloaded repository finds user by email",
            reloaded.get_by_email(EMAIL) is not None
            and reloaded.get_by_email(EMAIL).user_id == "user-1",
        )
        check(
            "reloaded repository finds user by id",
            reloaded.get_by_id("user-1") is not None,
        )
        reloaded_inactive = reloaded.get_by_id("user-inactive")
        check(
            "reloaded repository retains inactive state",
            reloaded_inactive is not None and reloaded_inactive.is_active is False,
        )
        reloaded_hash = reloaded.get_by_id("user-hash")
        check(
            "reloaded repository retains password hash",
            reloaded_hash is not None and reloaded_hash.password_hash == hashed,
        )

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(f"JSON User Repository Test {'PASSED' if all_passed else 'FAILED'}")
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())