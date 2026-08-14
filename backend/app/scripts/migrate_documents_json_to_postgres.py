"""One-time migration: documents.json registry -> PostgreSQL documents table.

Reads the JSON document registry (``backend/storage/documents.json`` by
default) and imports each document record into the PostgreSQL ``documents``
table, following the same ownership/workspace rules as
:class:`PostgresDocumentRepository`.

Scope:
- Migrates DOCUMENT REGISTRY records only.
- Does NOT migrate FAISS vectors, metadata.json, or physical PDFs. Those
  remain shared retrieval/storage infrastructure.
- Does NOT modify or delete documents.json or any other JSON source.

Behavior:
- One transaction: validate the source first, insert everything, commit once,
  roll back on any failure.
- Idempotent: a document id that already exists in PostgreSQL is skipped
  (reported as skipped), never duplicated.
- Preserves document id, filename, owner_id, workspace_id, uploaded_at, and
  the deleted state.
- Creates missing ``workspaces`` rows (``name = workspace_id``) following the
  existing repository rule, and cleans up nothing else.

Usage (from backend/):
    python -m app.scripts.migrate_documents_json_to_postgres
    python -m app.scripts.migrate_documents_json_to_postgres \
        --documents-json /path/to/documents.json \
        --database-url postgresql+psycopg://user:pass@host:5432/dbname

Exit status is 0 on success (including a clean no-op when documents.json is
absent), and non-zero when an import fails.
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db import models as db  # noqa: F401  (register tables on Base.metadata)
from app.services.document_registry import Document
from app.services.storage.json_file_store import JsonFileStore

REQUIRED_TABLES = {"documents", "workspaces"}


@dataclass
class MigrationResult:
    """Summary of a migration run."""

    records_found: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    workspaces_created: int = 0
    errors: list[str] = field(default_factory=list)


def _load_records(path: Path, result: MigrationResult) -> list[Document] | None:
    """Read and validate the JSON document registry.

    Args:
        path: The documents.json path.
        result: The migration result to update with counts/errors.

    Returns:
        The validated domain records, or None when the source is missing or
        invalid. Validation happens before any database work so a malformed
        source never leaves a partial import.
    """
    if not path.exists():
        result.errors.append(f"documents.json not found: {path}")
        return None

    raw = JsonFileStore.load(path, default=None)
    if not isinstance(raw, list):
        result.errors.append(
            f"{path} does not contain a JSON array of document records"
        )
        return None

    result.records_found = len(raw)

    records: list[Document] = []
    for item in raw:
        try:
            records.append(Document(**item))
        except Exception as exc:  # noqa: BLE001 - report and abort cleanly
            result.errors.append(f"invalid document record: {exc}")

    if result.errors:
        result.failed = result.records_found
        return None
    return records


def migrate(
    documents_json_path: str,
    database_url: str,
    session_factory=None,
) -> MigrationResult:
    """Import documents.json records into the PostgreSQL documents table.

    Args:
        documents_json_path: Path to the JSON document registry.
        database_url: SQLAlchemy database URL to connect to.
        session_factory: Optional session factory override (used by tests);
            when omitted, a factory is built from ``database_url``.

    Returns:
        A :class:`MigrationResult` describing the run.
    """
    result = MigrationResult()
    path = Path(documents_json_path)

    records = _load_records(path, result)
    if records is None:
        return result

    engine = None
    if session_factory is None:
        engine = create_engine(database_url, pool_pre_ping=True)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    try:
        with session_factory() as session:
            table_names = set(inspect(session.bind).get_table_names())
            missing = REQUIRED_TABLES - table_names
            if missing:
                result.errors.append(
                    "missing tables: "
                    + ", ".join(sorted(missing))
                    + "; run `alembic upgrade head` from backend/ first"
                )
                return result

            existing_ids = set(session.scalars(select(db.Document.id)).all())
            existing_workspaces = set(
                session.scalars(select(db.Workspace.id)).all()
            )
            now = datetime.now(timezone.utc)

            for record in records:
                if record.document_id in existing_ids:
                    result.skipped += 1
                    continue

                if record.workspace_id not in existing_workspaces:
                    session.add(
                        db.Workspace(
                            id=record.workspace_id,
                            name=record.workspace_id,
                            created_at=now,
                        )
                    )
                    existing_workspaces.add(record.workspace_id)
                    result.workspaces_created += 1

                uploaded_at = record.uploaded_at
                if uploaded_at.tzinfo is None:
                    uploaded_at = uploaded_at.replace(tzinfo=timezone.utc)
                else:
                    uploaded_at = uploaded_at.astimezone(timezone.utc)

                session.add(
                    db.Document(
                        id=record.document_id,
                        workspace_id=record.workspace_id,
                        filename=record.filename,
                        uploaded_at=uploaded_at,
                        chunk_count=record.chunk_count,
                        deleted=record.deleted,
                        owner_id=record.owner_id,
                    )
                )
                existing_ids.add(record.document_id)
                result.imported += 1

            session.commit()
    except Exception as exc:  # noqa: BLE001 - the session closes and rolls back
        result.errors.append(f"import failed; transaction rolled back: {exc}")
        result.failed = max(0, result.records_found - result.skipped)
        result.imported = 0
        result.workspaces_created = 0
    finally:
        if engine is not None:
            engine.dispose()

    return result


def main(argv: list[str] | None = None) -> int:
    """Run the migration from the command line."""
    parser = argparse.ArgumentParser(
        description=(
            "One-time migration of documents.json document records into the "
            "PostgreSQL documents table."
        )
    )
    parser.add_argument(
        "--documents-json",
        default=settings.documents_path,
        help="Path to documents.json (default: the configured documents path).",
    )
    parser.add_argument(
        "--database-url",
        default=settings.database_url,
        help="SQLAlchemy database URL (default: the configured DATABASE_URL).",
    )
    args = parser.parse_args(argv)

    path = Path(args.documents_json)
    if not path.exists():
        print(f"No documents.json found at: {path}")
        print("Nothing to import; exiting cleanly.")
        return 0

    if not args.database_url:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        print(
            "Set DATABASE_URL in backend/.env or pass --database-url.",
            file=sys.stderr,
        )
        return 1

    result = migrate(path, args.database_url)

    print("=" * 60)
    print("documents.json -> PostgreSQL document registry migration")
    print("=" * 60)
    print(f"Source: {path}")
    print(f"JSON records found: {result.records_found}")
    print(f"Workspaces created: {result.workspaces_created}")
    print(f"Imported: {result.imported}")
    print(f"Skipped (already exists): {result.skipped}")
    print(f"Failed: {result.failed}")
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print("=" * 60)

    if result.errors or result.failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())