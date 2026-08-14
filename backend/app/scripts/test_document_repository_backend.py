"""DocumentRepository backend-selection and interface-parity test.

Verifies that ``get_document_repository`` is backend-aware:

- ``persistence_backend="json"`` selects ``JsonDocumentRepository``,
- ``persistence_backend="postgres"`` selects ``PostgresDocumentRepository``,
- both implementations satisfy the ``DocumentRepository`` interface and
  behave identically (owner filtering, list/get/delete, soft deletion).

The PostgreSQL implementation is exercised against a temporary SQLite
database so the test runs without a reachable PostgreSQL server; the same
code paths run against PostgreSQL unchanged.

Usage (from backend/):
    python -m app.scripts.test_document_repository_backend

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_document_repository
from app.core.config import settings
from app.db import models as db  # noqa: F401  (register tables on Base.metadata)
from app.db.base import Base
from app.db.session import get_session_factory
from app.repositories.interfaces import DocumentRepository
from app.repositories.json.document_repository import JsonDocumentRepository
from app.repositories.postgres.document_repository import (
    PostgresDocumentRepository,
)
from app.services.document_registry import DocumentRegistry


def _exercise(repo: DocumentRepository) -> list[tuple[str, bool, str]]:
    """Run the shared interface assertions against a repository.

    Args:
        repo: A concrete DocumentRepository implementation.

    Returns:
        A list of (name, passed, detail) check results.
    """
    results: list[tuple[str, bool, str]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        results.append((name, passed, detail))

    # Registration.
    doc1 = repo.register(
        "default", "a.pdf", 3, owner_id="user-a", document_id="doc-1"
    )
    check(
        "register returns the domain document",
        doc1.document_id == "doc-1"
        and doc1.owner_id == "user-a"
        and doc1.filename == "a.pdf"
        and doc1.deleted is False,
    )
    repo.register("default", "b.pdf", 2, owner_id="user-a", document_id="doc-2")
    repo.register("default", "c.pdf", 1, owner_id="user-b", document_id="doc-3")

    # Owner-scoped listing.
    ids_a = {d.document_id for d in repo.list_documents("user-a")}
    check(
        "list is owner-scoped",
        ids_a == {"doc-1", "doc-2"} and "doc-3" not in ids_a,
        sorted(ids_a),
    )
    ids_b = {d.document_id for d in repo.list_documents("user-b")}
    check("other owner lists only their own", ids_b == {"doc-3"})

    # Owner-scoped get.
    check(
        "get returns own document",
        repo.get_document("doc-1", "user-a") is not None,
    )
    check(
        "get rejects another owner",
        repo.get_document("doc-1", "user-b") is None,
    )
    check(
        "get rejects unknown id",
        repo.get_document("nope", "user-a") is None,
    )

    # Exists.
    check("exists is true for a registered id", repo.exists("doc-1") is True)
    check("exists is false for an unknown id", repo.exists("nope") is False)

    # Soft deletion with owner enforcement.
    check(
        "delete rejects another owner",
        repo.delete_document("doc-3", "user-a") is False,
    )
    check("delete marks own document", repo.delete_document("doc-1", "user-a") is True)
    check(
        "second delete returns False",
        repo.delete_document("doc-1", "user-a") is False,
    )
    check(
        "is_deleted is true after delete",
        repo.is_deleted("doc-1") is True,
    )
    check(
        "is_deleted is false for a live document",
        repo.is_deleted("doc-2") is False,
    )
    check(
        "is_deleted is false for an unknown id",
        repo.is_deleted("nope") is False,
    )
    # Deleted documents remain visible to their owner (existing semantics).
    check(
        "deleted document still visible to its owner",
        repo.get_document("doc-1", "user-a") is not None,
    )
    return results


def main() -> int:
    """Run the backend-selection and interface-parity test."""
    print("=" * 60)
    print("DocumentRepository Backend Selection Test")
    print("=" * 60)

    all_results: list[tuple[str, bool, str]] = []
    checks = {"failed": False}

    def report(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        all_results.append((name, passed, detail))
        if not passed:
            checks["failed"] = True

    # 1. Interface satisfaction.
    report(
        "JsonDocumentRepository implements DocumentRepository",
        issubclass(JsonDocumentRepository, DocumentRepository),
    )
    report(
        "PostgresDocumentRepository implements DocumentRepository",
        issubclass(PostgresDocumentRepository, DocumentRepository),
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        sqlite_url = f"sqlite:///{(tmp_dir / 'documents.db').as_posix()}"

        # 2. DI selection for persistence_backend="json".
        settings.persistence_backend = "json"
        get_document_repository.cache_clear()
        json_repo = get_document_repository()
        report(
            "persistence_backend=json selects JsonDocumentRepository",
            isinstance(json_repo, JsonDocumentRepository),
            type(json_repo).__name__,
        )

        # 3. DI selection for persistence_backend="postgres".
        settings.persistence_backend = "postgres"
        settings.database_url = sqlite_url
        get_session_factory.cache_clear()
        get_document_repository.cache_clear()
        pg_repo = get_document_repository()
        report(
            "persistence_backend=postgres selects PostgresDocumentRepository",
            isinstance(pg_repo, PostgresDocumentRepository),
            type(pg_repo).__name__,
        )

        # 4. Behavioral parity across both implementations.
        json_registry = DocumentRegistry(tmp_dir / "registry.json")
        json_impl = JsonDocumentRepository(json_registry)
        json_results = _exercise(json_impl)
        print(f"\n  JsonDocumentRepository behavior ({len(json_results)} checks):")
        for name, passed, detail in json_results:
            report(f"  {name}", passed, detail)

        engine = create_engine(sqlite_url)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        Base.metadata.create_all(engine)
        pg_impl = PostgresDocumentRepository(session_factory)
        pg_results = _exercise(pg_impl)
        print(f"\n  PostgresDocumentRepository behavior ({len(pg_results)} checks):")
        for name, passed, detail in pg_results:
            report(f"  {name}", passed, detail)

        engine.dispose()

    # Restore the process-global settings defaults.
    settings.persistence_backend = "json"

    print("\n" + "=" * 60)
    print(
        "DocumentRepository Backend Test "
        + ("PASSED" if not checks["failed"] else "FAILED")
    )
    print("=" * 60)
    return 1 if checks["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
