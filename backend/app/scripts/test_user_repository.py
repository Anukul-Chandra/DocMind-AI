"""PostgreSQL user repository smoke test.

Verifies the production-ready user persistence layer against the configured
PostgreSQL:

    - creating a user persists the account and returns the domain model,
    - users can be retrieved by email and by id,
    - duplicate email addresses are rejected by the database constraint,
    - the stored password hash round-trips and is never the plaintext,
    - inactive accounts retain their disabled state.

Usage (from backend/):
    python -m app.scripts.test_user_repository

Exit status is non-zero if any check fails.
"""

import sys
import uuid

from sqlalchemy import inspect, select, text

from app.db import models as db  # noqa: F401  (register tables on Base.metadata)
from app.db.session import get_session_factory
from app.repositories.postgres.user_repository import PostgresUserRepository
from app.services.auth.password import PasswordService

EMAIL = "test.user@example.com"


def _cleanup(session, user_ids: list[str]) -> None:
    """Delete test users from the database by id."""
    session.execute(
        text("DELETE FROM users WHERE id = ANY(:ids)"),
        {"ids": user_ids},
    )
    session.commit()


def main() -> int:
    """Run the user repository test."""
    print("=" * 60)
    print("PostgreSQL User Repository Test")
    print("=" * 60)

    session_factory = get_session_factory()
    repository = PostgresUserRepository(session_factory)
    test_user_ids: list[str] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        if not passed:
            checks["failed"] = True

    checks: dict[str, bool] = {"failed": False}

    try:
        # Check 1: database unique constraint on email exists (requirement 3).
        with session_factory() as session:
            indexes = inspect(session.connection()).get_unique_constraints("users")
        email_unique = any(
            constraint.get("column_names") == ["email"]
            for constraint in indexes
        )
        check(
            "unique constraint on email",
            email_unique,
            "users.email" if email_unique else "missing unique constraint",
        )

        # Check 2: creating a user persists the account and returns it.
        user_id = str(uuid.uuid4())
        test_user_ids.append(user_id)
        password_hash = "scrypt$16384$8$1$salted$hashhash"
        created = repository.create(
            email=EMAIL,
            password_hash=password_hash,
            user_id=user_id,
        )
        check(
            "create user returns the domain user",
            created.user_id == user_id
            and created.email == EMAIL
            and created.password_hash == password_hash
            and created.is_active is True,
        )

        # Check 3: the row is actually persisted.
        with session_factory() as session:
            row = session.get(db.User, user_id)
        check(
            "created user is persisted",
            row is not None and row.email == EMAIL,
        )

        # Check 4: retrieving by email.
        found = repository.get_by_email(EMAIL)
        check(
            "find user by email",
            found is not None
            and found.user_id == user_id
            and found.email == EMAIL,
        )

        # Check 5: retrieving by id.
        found = repository.get_by_id(user_id)
        check(
            "find user by id",
            found is not None and found.email == EMAIL,
        )

        # Check 6: unknown lookups return None.
        check(
            "unknown email returns None",
            repository.get_by_email("nobody@example.com") is None,
        )
        check(
            "unknown id returns None",
            repository.get_by_id("does-not-exist") is None,
        )

        # Check 7: password hash persistence (never the plaintext).
        plaintext = "correct horse battery staple"
        hashed = PasswordService().hash(plaintext)
        other_id = str(uuid.uuid4())
        test_user_ids.append(other_id)
        repository.create(email="hash.roundtrip@example.com", password_hash=hashed, user_id=other_id)
        with session_factory() as session:
            stored = session.scalar(
                select(db.User.password_hash).where(db.User.id == other_id)
            )
        check(
            "stored value equals the hash, not the plaintext",
            stored == hashed and stored != plaintext,
        )

        # Check 8: inactive user state is retained.
        inactive_id = str(uuid.uuid4())
        test_user_ids.append(inactive_id)
        repository.create(
            email="inactive@example.com",
            password_hash=hashed,
            user_id=inactive_id,
            is_active=False,
        )
        inactive = repository.get_by_email("inactive@example.com")
        check(
            "inactive user state is retained",
            inactive is not None and inactive.is_active is False,
        )

        # Check 9: duplicate email is rejected.
        duplicate_id = str(uuid.uuid4())
        test_user_ids.append(duplicate_id)
        try:
            repository.create(
                email=EMAIL,
                password_hash=password_hash,
                user_id=duplicate_id,
            )
            check("duplicate email rejection", False, "no error raised")
        except ValueError:
            check("duplicate email rejection", True)
        # A failed duplicate must not have been committed.
        check(
            "duplicate is not persisted",
            repository.get_by_id(duplicate_id) is None,
        )

    except Exception as exc:  # noqa: BLE001 - manual test should not crash
        print(f"\n[FAIL] Unexpected error: {type(exc).__name__}: {exc}")
        checks["failed"] = True
    finally:
        with session_factory() as session:
            _cleanup(session, test_user_ids)

    print("\n" + "=" * 60)
    print("User Repository Test " + ("FAILED" if checks["failed"] else "PASSED"))
    print("=" * 60)
    return 1 if checks["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())