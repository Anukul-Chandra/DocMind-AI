"""Alembic migration regression test: Postgres data-parity columns.

Verifies that revision ``c7a9d31e5b42`` ("fix postgres data parity") upgrades
safely when the ``documents`` and ``request_logs`` tables already contain rows:

- the migration succeeds and adds the expected columns,
- pre-existing documents receive ``classification = 'unknown'`` and
  ``extracted_data = NULL``,
- pre-existing request logs receive the empty ``method``/``path``/``user_id``
  and ``status_code = 0`` defaults,
- future rows inserted through the application still get the ORM defaults,
- the downgrade is reversible.

The test runs the real Alembic migration chain against a temporary SQLite
database, mirroring ``test_migration_auth_fields``. ``DATABASE_URL`` is
blanked before any application import so the Alembic environment targets the
test database.

Usage (from backend/):
    python -m app.scripts.test_migration_data_parity

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
REVISION_BEFORE_PARITY = "929856ee0161"
REVISION_HEAD = "c7a9d31e5b42"


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config targeting a specific database URL."""
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _column(engine, table: str, column: str) -> dict | None:
    """Return the column definition for a table, or None if absent."""
    for col in inspect(engine).get_columns(table):
        if col["name"] == column:
            return col
    return None


def main() -> int:
    """Run the migration regression test."""
    print("=" * 60)
    print("Alembic Migration Test (Postgres data-parity columns)")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "parity_migration.db"
        url = f"sqlite:///{db_path.as_posix()}"
        engine = create_engine(url)
        cfg = _alembic_config(url)

        # Start just before the parity revision, then seed populated
        # documents and request_logs tables.
        command.upgrade(cfg, REVISION_BEFORE_PARITY)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO workspaces (id, name, created_at) "
                    "VALUES ('default', 'default', :created_at)"
                ),
                {"created_at": "2026-08-02 12:00:00+00:00"},
            )
            conn.execute(
                text(
                    "INSERT INTO documents "
                    "(id, workspace_id, filename, uploaded_at, chunk_count, "
                    "deleted, owner_id) "
                    "VALUES (:id, 'default', :filename, :uploaded_at, :chunks, "
                    ":deleted, :owner_id)"
                ),
                {
                    "id": "existing-doc",
                    "filename": "a.pdf",
                    "uploaded_at": "2026-08-02 12:00:00+00:00",
                    "chunks": 3,
                    "deleted": False,
                    "owner_id": "user-a",
                },
            )
            conn.execute(
                text(
                    "INSERT INTO request_logs "
                    "(request_id, timestamp, workspace_id, conversation_id, "
                    "provider, model, question, retrieved_chunk_count, "
                    "response_time_ms, success) "
                    "VALUES ('existing-log', :timestamp, 'default', '', '', '', "
                    "'', 0, 1.5, 1)"
                ),
                {"timestamp": "2026-08-02 12:00:00+00:00"},
            )

        # Run the parity migration (to head).
        command.upgrade(cfg, REVISION_HEAD)

        # The new documents columns must exist.
        classification = _column(engine, "documents", "classification")
        check(
            "documents.classification column added",
            classification is not None,
        )
        check(
            "documents.classification is NOT NULL",
            classification is not None and classification["nullable"] is False,
        )
        check(
            "documents.extracted_data column added",
            _column(engine, "documents", "extracted_data") is not None,
        )
        # The new request_logs columns must exist.
        for column in ("method", "path", "status_code", "user_id"):
            check(
                f"request_logs.{column} column added",
                _column(engine, "request_logs", column) is not None,
            )

        # Pre-existing documents received valid values.
        with engine.connect() as conn:
            doc = conn.execute(
                text(
                    "SELECT classification, extracted_data "
                    "FROM documents WHERE id = :id"
                ),
                {"id": "existing-doc"},
            ).one()
        check(
            "existing document classification defaults to unknown",
            doc.classification == "unknown",
        )
        check(
            "existing document extracted_data defaults to NULL",
            doc.extracted_data is None,
        )

        # Pre-existing request logs received valid values.
        with engine.connect() as conn:
            log_row = conn.execute(
                text(
                    "SELECT method, path, status_code, user_id "
                    "FROM request_logs WHERE request_id = :rid"
                ),
                {"rid": "existing-log"},
            ).one()
        check(
            "existing request log method defaults to empty",
            log_row.method == "",
        )
        check(
            "existing request log path defaults to empty",
            log_row.path == "",
        )
        check(
            "existing request log status_code defaults to 0",
            log_row.status_code == 0,
        )
        check(
            "existing request log user_id defaults to empty",
            log_row.user_id == "",
        )

        # Future rows inserted through the application still get defaults.
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session:
            session.add(
                db.Document(
                    id="future-doc",
                    workspace_id="default",
                    filename="b.pdf",
                    chunk_count=1,
                    owner_id="user-b",
                )
            )
            session.commit()
        with factory() as session:
            future = session.execute(
                text(
                    "SELECT classification, extracted_data "
                    "FROM documents WHERE id = :id"
                ),
                {"id": "future-doc"},
            ).one()
        check(
            "future document classification default applies",
            future.classification == "unknown",
        )
        check(
            "future document extracted_data default applies",
            future.extracted_data is None,
        )

        # Downgrade is reversible.
        command.downgrade(cfg, REVISION_BEFORE_PARITY)
        check(
            "downgrade drops documents.classification",
            _column(engine, "documents", "classification") is None,
        )
        check(
            "downgrade drops documents.extracted_data",
            _column(engine, "documents", "extracted_data") is None,
        )
        for column in ("method", "path", "status_code", "user_id"):
            check(
                f"downgrade drops request_logs.{column}",
                _column(engine, "request_logs", column) is None,
            )

        engine.dispose()

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print("Migration Test " + ("PASSED" if all_passed else "FAILED"))
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())