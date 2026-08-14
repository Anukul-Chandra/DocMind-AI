"""Alembic migration regression test: authentication fields on populated users.

Verifies that revision ``081ffd9766a9`` ("add user authentication fields")
upgrades safely when the ``users`` table already contains rows:

- the migration succeeds,
- pre-existing users receive valid values for the new columns,
- the new columns end up NOT NULL,
- future users inserted through the application still get the ORM defaults,
- the downgrade is reversible.

The test runs the real Alembic migration chain against a temporary SQLite
database, which is the practical way to exercise a populated ``users`` table
without a PostgreSQL server. ``DATABASE_URL`` is blanked before any
application import so the Alembic environment targets the test database.

Usage (from backend/):
    python -m app.scripts.test_migration_auth_fields

Exit status is non-zero if any check fails.
"""

import os
import sys
import tempfile
from pathlib import Path

# Blank the configured database URL so the Alembic environment uses the test
# database URL instead of the value in backend/.env (env vars override .env).
os.environ["DATABASE_URL"] = ""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.db import models as db  # noqa: F401  (register tables on Base.metadata)

REVISION_INITIAL = "111bedfdea17"
REVISION_AUTH_FIELDS = "081ffd9766a9"
REVISION_DOC_OWNERSHIP = "929856ee0161"


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config targeting a specific database URL."""
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _column_nullable(engine, column: str) -> bool:
    """Return whether a users column is nullable."""
    for col in inspect(engine).get_columns("users"):
        if col["name"] == column:
            return col["nullable"]
    raise AssertionError(f"column {column!r} not found in users")


def main() -> int:
    """Run the migration regression test."""
    print("=" * 60)
    print("Alembic Migration Test (authentication fields on populated users)")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "migration.db"
        url = f"sqlite:///{db_path.as_posix()}"
        engine = create_engine(url)
        cfg = _alembic_config(url)

        # Start at the schema before authentication fields existed, then seed
        # a populated users table.
        command.upgrade(cfg, REVISION_INITIAL)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, created_at) "
                    "VALUES (:id, :email, :created_at)"
                ),
                {
                    "id": "existing-user",
                    "email": "existing@example.com",
                    "created_at": "2026-08-02 12:00:00+00:00",
                },
            )

        # Run the authentication-fields migration (plus the later revision).
        command.upgrade(cfg, REVISION_DOC_OWNERSHIP)

        # The migration must have succeeded and produced NOT NULL columns.
        check(
            "password_hash is NOT NULL",
            _column_nullable(engine, "password_hash") is False,
        )
        check(
            "updated_at is NOT NULL",
            _column_nullable(engine, "updated_at") is False,
        )
        check(
            "is_active is NOT NULL",
            _column_nullable(engine, "is_active") is False,
        )

        # Pre-existing user received valid values.
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT password_hash, updated_at, created_at, is_active "
                    "FROM users WHERE id = :id"
                ),
                {"id": "existing-user"},
            ).one()
        check(
            "existing user got an empty password_hash",
            row.password_hash == "",
        )
        check(
            "existing user got a valid updated_at",
            row.updated_at is not None,
        )
        check(
            "existing user updated_at backfilled from created_at",
            row.updated_at == row.created_at,
        )
        check(
            "existing user is_active backfilled to true",
            bool(row.is_active) is True,
        )

        # A future user inserted through the application still gets defaults.
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session:
            user = db.User(
                id="future-user",
                email="future@example.com",
                password_hash="stored-hash",
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        check(
            "future user password_hash persists",
            user.password_hash == "stored-hash",
        )
        check(
            "future user updated_at default applies",
            user.updated_at is not None,
        )
        check(
            "future user is_active default applies",
            user.is_active is True,
        )
        with factory() as session:
            session.execute(
                text("DELETE FROM users WHERE id = :id"),
                {"id": "future-user"},
            )
            session.commit()

        # Downgrade is reversible.
        command.downgrade(cfg, REVISION_INITIAL)
        check(
            "downgrade drops password_hash",
            "password_hash" not in [c["name"] for c in inspect(engine).get_columns("users")],
        )
        check(
            "downgrade drops updated_at",
            "updated_at" not in [c["name"] for c in inspect(engine).get_columns("users")],
        )
        check(
            "downgrade drops is_active",
            "is_active" not in [c["name"] for c in inspect(engine).get_columns("users")],
        )

        engine.dispose()

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print("Migration Test " + ("PASSED" if all_passed else "FAILED"))
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
