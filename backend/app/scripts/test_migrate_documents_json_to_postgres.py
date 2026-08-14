"""Migration utility regression test: documents.json -> PostgreSQL.

Verifies the one-time import utility behavior:

    A. Import multiple JSON documents.
    B. Preserve document IDs.
    C. Preserve owner_id (including legacy records without one).
    D. Preserve filename.
    E. Preserve deletion state.
    F. Workspace relationships remain valid (workspace rows are created).
    G. Running import twice does not duplicate records.
    H. Existing PostgreSQL records are skipped safely.
    I. JSON source file remains unchanged.
    J. A mid-batch failure rolls back the whole transaction.

The migration runs against a temporary SQLite database (via the script's
``session_factory`` seam) so the test runs without a reachable PostgreSQL
server; the exact same import code paths apply to PostgreSQL.

Usage (from backend/):
    python -m app.scripts.test_migrate_documents_json_to_postgres

Exit status is non-zero if any check fails.
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.db import models as db  # noqa: F401  (register tables on Base.metadata)
from app.db.base import Base
from app.scripts.migrate_documents_json_to_postgres import migrate

RECORDS = [
    {
        "document_id": "doc-1",
        "workspace_id": "default",
        "filename": "a.pdf",
        "uploaded_at": "2026-08-02T10:00:00Z",
        "chunk_count": 3,
        "deleted": False,
        "owner_id": "user-a",
    },
    {
        "document_id": "doc-2",
        "workspace_id": "default",
        "filename": "b.pdf",
        "uploaded_at": "2026-08-02T11:00:00Z",
        "chunk_count": 2,
        "deleted": True,
        "owner_id": "user-b",
    },
    # Legacy record: no owner_id, no deleted field.
    {
        "document_id": "doc-3",
        "workspace_id": "legacy",
        "filename": "c.pdf",
        "uploaded_at": "2026-08-02T12:00:00Z",
        "chunk_count": 1,
    },
]


def _utc_naive(value: datetime) -> datetime:
    """Return a timezone-normalized naive UTC datetime for comparisons."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _write_json(path: Path, records: list[dict]) -> None:
    """Write records to a documents.json file."""
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


def main() -> int:
    """Run the migration utility test."""
    print("=" * 60)
    print("documents.json -> PostgreSQL Migration Test")
    print("=" * 60)

    checks: dict[str, bool] = {"failed": False}

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        if not passed:
            checks["failed"] = True

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # ---- Import / preservation scenarios (A-F) on one database. ----
        db_path = tmp / "main.db"
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        Base.metadata.create_all(engine)

        source = tmp / "documents.json"
        _write_json(source, RECORDS)
        before = source.read_bytes()

        result = migrate(str(source), "sqlite://", session_factory=session_factory)

        check(
            "A. all JSON records found",
            result.records_found == 3,
            f"records_found={result.records_found}",
        )
        check(
            "A. all records imported",
            result.imported == 3
            and result.skipped == 0
            and result.failed == 0,
            f"imported={result.imported} skipped={result.skipped} failed={result.failed}",
        )

        with session_factory() as session:
            rows = {r.id: r for r in session.scalars(select(db.Document))}
        check(
            "B. document IDs preserved",
            set(rows) == {"doc-1", "doc-2", "doc-3"},
            sorted(rows),
        )
        check(
            "C. owner_id preserved",
            rows["doc-1"].owner_id == "user-a"
            and rows["doc-2"].owner_id == "user-b"
            and rows["doc-3"].owner_id == "",
        )
        check(
            "D. filename preserved",
            rows["doc-1"].filename == "a.pdf"
            and rows["doc-2"].filename == "b.pdf"
            and rows["doc-3"].filename == "c.pdf",
        )
        check(
            "E. deletion state preserved",
            rows["doc-1"].deleted is False
            and rows["doc-2"].deleted is True
            and rows["doc-3"].deleted is False,
        )
        check(
            "uploaded_at preserved",
            _utc_naive(rows["doc-1"].uploaded_at)
            == datetime(2026, 8, 2, 10, 0),
            str(rows["doc-1"].uploaded_at),
        )

        with session_factory() as session:
            workspaces = session.scalars(select(db.Workspace.id)).all()
        check(
            "F. workspace rows created for referenced workspaces",
            sorted(workspaces) == ["default", "legacy"],
            sorted(workspaces),
        )

        # ---- G. Idempotency: running again must not duplicate. ----
        result2 = migrate(str(source), "sqlite://", session_factory=session_factory)
        check(
            "G. second run imports nothing and skips all",
            result2.imported == 0 and result2.skipped == 3,
            f"imported={result2.imported} skipped={result2.skipped}",
        )
        with session_factory() as session:
            count = len(session.scalars(select(db.Document.id)).all())
        check(
            "G. no duplicate records after second run",
            count == 3,
            f"count={count}",
        )

        # ---- H. Existing PostgreSQL records are skipped safely. ----
        with session_factory() as session:
            session.add(
                db.Document(
                    id="doc-pre",
                    workspace_id="default",
                    filename="pre.pdf",
                    uploaded_at=datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc),
                    chunk_count=1,
                    deleted=False,
                    owner_id="pre-owner",
                )
            )
            session.commit()
        source_h = tmp / "documents_h.json"
        _write_json(
            source_h,
            [
                {"document_id": "doc-pre", "workspace_id": "default",
                 "filename": "pre.pdf", "uploaded_at": "2026-08-01T09:00:00Z",
                 "chunk_count": 1, "owner_id": "pre-owner"},
                {"document_id": "doc-4", "workspace_id": "default",
                 "filename": "d.pdf", "uploaded_at": "2026-08-03T09:00:00Z",
                 "chunk_count": 1, "owner_id": "user-c"},
            ],
        )
        result3 = migrate(str(source_h), "sqlite://", session_factory=session_factory)
        check(
            "H. pre-existing record skipped, new record imported",
            result3.skipped == 1 and result3.imported == 1,
            f"imported={result3.imported} skipped={result3.skipped}",
        )
        with session_factory() as session:
            pre_rows = session.scalars(
                select(db.Document).where(db.Document.id == "doc-pre")
            ).all()
        check(
            "H. pre-existing record not duplicated",
            len(pre_rows) == 1,
            f"rows={len(pre_rows)}",
        )

        # ---- I. JSON source file remains unchanged. ----
        check("I. JSON source file unchanged", source.read_bytes() == before)

        # ---- J. Mid-batch failure rolls back the whole transaction. ----
        rollback_db = tmp / "rollback.db"
        rb_engine = create_engine(f"sqlite:///{rollback_db.as_posix()}")
        rb_factory = sessionmaker(bind=rb_engine, expire_on_commit=False)
        Base.metadata.create_all(rb_engine)
        # Recreate documents with a CHECK so the second insert must fail.
        with rb_engine.begin() as conn:
            conn.execute(text("DROP TABLE documents"))
            conn.execute(
                text(
                    "CREATE TABLE documents ("
                    "id VARCHAR(64) PRIMARY KEY, "
                    "workspace_id VARCHAR(64) NOT NULL, "
                    "filename VARCHAR(512) NOT NULL, "
                    "uploaded_at DATETIME NOT NULL, "
                    "chunk_count INTEGER NOT NULL DEFAULT 0, "
                    "deleted BOOLEAN NOT NULL DEFAULT 0, "
                    "owner_id VARCHAR(64) NOT NULL DEFAULT '', "
                    "CHECK (filename <> 'bad.pdf'))"
                )
            )
        source_j = tmp / "documents_j.json"
        _write_json(
            source_j,
            [
                {"document_id": "rb-1", "workspace_id": "default",
                 "filename": "ok.pdf", "uploaded_at": "2026-08-04T09:00:00Z",
                 "chunk_count": 1, "owner_id": "user-x"},
                {"document_id": "rb-2", "workspace_id": "default",
                 "filename": "bad.pdf", "uploaded_at": "2026-08-04T10:00:00Z",
                 "chunk_count": 1, "owner_id": "user-y"},
            ],
        )
        result4 = migrate(str(source_j), "sqlite://", session_factory=rb_factory)
        with rb_factory() as session:
            doc_count = len(session.scalars(select(db.Document.id)).all())
            ws_count = len(session.scalars(select(db.Workspace.id)).all())
        check(
            "J. failure reports the failed batch",
            result4.failed == 2 and result4.imported == 0,
            f"imported={result4.imported} failed={result4.failed}",
        )
        check(
            "J. documents rolled back (no partial import)",
            doc_count == 0,
            f"documents={doc_count}",
        )
        check(
            "J. workspace creation rolled back too",
            ws_count == 0,
            f"workspaces={ws_count}",
        )
        check(
            "J. rollback error reported",
            any("rolled back" in e for e in result4.errors),
            result4.errors[:1],
        )

        engine.dispose()
        rb_engine.dispose()

    print("\n" + "=" * 60)
    print("Migration Test " + ("PASSED" if not checks["failed"] else "FAILED"))
    print("=" * 60)
    return 1 if checks["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
