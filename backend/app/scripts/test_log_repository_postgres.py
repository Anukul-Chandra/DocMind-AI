"""PostgreSQL log repository regression test.

Verifies the transaction fix for :class:`PostgresLogRepository`: successful
writes are committed so a fresh session observes them, and a failing write
remains best-effort (it never propagates to the caller).

The repository is exercised through a real SQLAlchemy session factory. The
schema is created on a temporary SQLite database by default so the test runs
even when PostgreSQL is unreachable; the same code paths run against
PostgreSQL unchanged.

Usage (from backend/):
    python -m app.scripts.test_log_repository_postgres

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import models as db  # noqa: F401  (register tables on Base.metadata)
from app.db.base import Base
from app.repositories.postgres.log_repository import PostgresLogRepository
from app.services.logging.request_logger import RequestLogEntry


def main() -> int:
    """Run the log repository regression test."""
    print("=" * 60)
    print("PostgreSQL Log Repository Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "logs.db"
        url = f"sqlite:///{db_path.as_posix()}"
        engine = create_engine(url)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        Base.metadata.create_all(engine)

        repository = PostgresLogRepository(session_factory)
        entry = RequestLogEntry(
            request_id="req-1",
            timestamp="2026-08-14T10:00:00+00:00",
            workspace_id="ws-1",
            conversation_id="conv-1",
            provider="mock",
            model="mock-model",
            question="what is x?",
            retrieved_chunk_count=3,
            response_time_ms=12.5,
            success=True,
        )

        # A successful write persists across sessions.
        repository.log(entry)
        with session_factory() as session:
            row = session.scalar(
                select(db.RequestLogEntry).where(
                    db.RequestLogEntry.request_id == "req-1"
                )
            )
        check(
            "log entry persists in a fresh session",
            row is not None
            and row.workspace_id == "ws-1"
            and row.question == "what is x?"
            and row.success is True
            and row.error_message is None,
        )

        # A failed write (missing table) must not propagate.
        with session_factory() as session:
            db.RequestLogEntry.__table__.drop(session.bind)
        try:
            repository.log(entry)
            check("failing log write is best-effort", True)
        except Exception as exc:  # noqa: BLE001
            check(
                "failing log write is best-effort",
                False,
                f"raised {type(exc).__name__}: {exc}",
            )

        engine.dispose()

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print("Log Repository Test " + ("PASSED" if all_passed else "FAILED"))
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
