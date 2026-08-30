"""Database foundation smoke test.

Verifies the SQLAlchemy + Alembic setup against the configured PostgreSQL:

    - a working database connection,
    - the expected tables exist (as defined by ``Base.metadata``),
    - the session factory produces a usable session (read/write round trip).

Usage (from backend/):
    python -m app.scripts.test_database

Exit status is non-zero if any check fails.
"""

import sys

from sqlalchemy import inspect, select, text

from app.core.config import settings
from app.db import models  # noqa: F401  (register tables on Base.metadata)
from app.db.base import Base
from app.db.session import get_session_factory
from app.db.models import Workspace


def main() -> int:
    """Run the database smoke test."""
    print("=" * 60)
    print("Database Foundation Test")
    print("=" * 60)

    if not settings.database_url:
        print("\n[FAIL] DATABASE_URL is not configured.")
        print("Add DATABASE_URL to backend/.env and try again.")
        return 1

    print(f"\nTarget: {settings.database_url}")

    try:
        session_factory = get_session_factory()
    except RuntimeError as exc:
        print(f"\n[FAIL] Could not build session factory: {exc}")
        return 1

    # Check 1: database connection.
    try:
        with session_factory() as session:
            version = session.execute(text("SELECT version()")).scalar()
    except Exception as exc:  # noqa: BLE001
        print(f"\n[FAIL] Database connection failed: {exc}")
        return 1
    print(f"\n[OK] Database connection established: {version.split(',')[0]}")

    # Check 2: expected tables exist.
    try:
        with session_factory() as session:
            existing = set(inspect(session.connection()).get_table_names())
    except Exception as exc:  # noqa: BLE001
        print(f"\n[FAIL] Could not inspect database tables: {exc}")
        return 1

    expected = set(Base.metadata.tables)
    missing = expected - existing
    if missing:
        pgvector_missing = True
        try:
            with session_factory() as session:
                result = session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
                if result.fetchall():
                    pgvector_missing = False
        except Exception:
            pass
        if pgvector_missing and missing == {"vector_chunks"}:
            print(f"\n[WARN] pgvector extension not installed; skipping vector_chunks table check.")
            expected = expected - {"vector_chunks"}
            missing = expected - existing
        if missing:
            print(f"\n[FAIL] Missing tables: {sorted(missing)}")
            print("Run `alembic upgrade head` from backend/ to apply migrations.")
            return 1
    print(f"\n[OK] All {len(expected)} tables exist: {sorted(expected)}")

    # Check 3: session read/write round trip.
    workspace_id = "db-smoke-test"
    try:
        with session_factory() as session:
            session.add(Workspace(id=workspace_id, name="smoke test"))
            session.commit()
            row = session.scalar(
                select(Workspace.id).where(Workspace.id == workspace_id)
            )
            if row != workspace_id:
                raise AssertionError("written workspace could not be read back")
            session.execute(
                text("DELETE FROM workspaces WHERE id = :wid"),
                {"wid": workspace_id},
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"\n[FAIL] Session round trip failed: {exc}")
        return 1
    print("\n[OK] Session factory produces a working session (read/write).")

    print("\n" + "=" * 60)
    print("All database checks passed.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
