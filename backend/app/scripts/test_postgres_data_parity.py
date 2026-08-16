"""Postgres data-parity regression test.

Verifies the two persistence gaps fixed by revision ``c7a9d31e5b42``:

1. Document ``classification`` and ``extracted_data`` survive a save -> reload
   round trip through :class:`PostgresDocumentRepository` (matching the
   JSON-backed behavior).
2. Request logs persist ``method``, ``path``, ``status_code``, and ``user_id``
   through :class:`PostgresLogRepository`.

The repository is exercised through a real SQLAlchemy session factory with
the schema created on a temporary SQLite database, so the test runs without a
reachable PostgreSQL server; the same code paths apply to PostgreSQL
unchanged (mirroring the existing repository test style).

Usage (from backend/):
    python -m app.scripts.test_postgres_data_parity

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import models as db  # noqa: F401  (register tables on Base.metadata)
from app.db.base import Base
from app.repositories.postgres.document_repository import (
    PostgresDocumentRepository,
)
from app.repositories.postgres.log_repository import PostgresLogRepository
from app.services.logging.request_logger import RequestLogEntry


def main() -> int:
    """Run the data-parity regression test."""
    print("=" * 60)
    print("Postgres Data Parity Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "parity.db"
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        Base.metadata.create_all(engine)

        # ---- 1. Document classification / extracted_data round trip. ----
        document_repo = PostgresDocumentRepository(session_factory)
        extracted = {"name": "Ada", "skills": ["python", "sql"]}
        created = document_repo.register(
            "default",
            "resume.pdf",
            4,
            owner_id="user-a",
            document_id="doc-parity",
            classification="resume",
            extracted_data=extracted,
        )
        check(
            "register returns classification and extracted_data",
            created.classification == "resume"
            and created.extracted_data == extracted,
        )

        reloaded = document_repo.get_document("doc-parity", "user-a")
        check(
            "classification survives Postgres save -> reload",
            reloaded is not None and reloaded.classification == "resume",
            getattr(reloaded, "classification", None),
        )
        check(
            "extracted_data survives Postgres save -> reload",
            reloaded is not None and reloaded.extracted_data == extracted,
            getattr(reloaded, "extracted_data", None),
        )

        listed = document_repo.list_documents("user-a")
        check(
            "list_documents returns persisted classification",
            any(d.document_id == "doc-parity" and d.classification == "resume"
                for d in listed),
        )

        # Defaults when classification/extracted_data are omitted.
        defaulted = document_repo.register(
            "default",
            "plain.pdf",
            1,
            owner_id="user-a",
            document_id="doc-default",
        )
        check(
            "omitted classification defaults to unknown",
            defaulted.classification == "unknown"
            and defaulted.extracted_data is None,
        )

        # Raw row inspection: values are actually stored on the row.
        with session_factory() as session:
            row = session.scalar(
                select(db.Document).where(db.Document.id == "doc-parity")
            )
        check(
            "raw documents row stores both new fields",
            row is not None
            and row.classification == "resume"
            and row.extracted_data == extracted,
        )

        # ---- 2. Request log method/path/status_code/user_id round trip. ----
        log_repo = PostgresLogRepository(session_factory)
        entry = RequestLogEntry(
            request_id="req-parity",
            timestamp="2026-08-16T12:00:00+00:00",
            method="POST",
            path="/documents/upload",
            status_code=200,
            user_id="user-a",
            workspace_id="default",
            response_time_ms=4.5,
            success=True,
        )
        log_repo.log(entry)
        with session_factory() as session:
            row = session.scalar(
                select(db.RequestLogEntry).where(
                    db.RequestLogEntry.request_id == "req-parity"
                )
            )
        check(
            "request log persists method",
            row is not None and row.method == "POST",
            getattr(row, "method", None),
        )
        check(
            "request log persists path",
            row is not None and row.path == "/documents/upload",
            getattr(row, "path", None),
        )
        check(
            "request log persists status_code",
            row is not None and row.status_code == 200,
            getattr(row, "status_code", None),
        )
        check(
            "request log persists user_id",
            row is not None and row.user_id == "user-a",
            getattr(row, "user_id", None),
        )

        engine.dispose()

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print("Data Parity Test " + ("PASSED" if all_passed else "FAILED"))
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())