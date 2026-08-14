"""Focused regression test for DocumentRegistry.register() failure atomicity.

Verifies that when JsonFileStore.save() fails during register():

* the exception is still raised,
* the new document is removed from the in-memory registry,
* the previously persisted documents remain unchanged,
* a fresh registry instance sees only the previously persisted documents,
* the registry remains usable after the failure.

Also confirms the PostgreSQL backend keeps its unchanged atomic behavior.

Usage (from backend/):
    python -m app.scripts.test_register_failure_atomicity

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import models as db  # noqa: F401  (register tables on Base.metadata)
from app.db.base import Base
from app.repositories.json.document_repository import JsonDocumentRepository
from app.repositories.postgres.document_repository import PostgresDocumentRepository
from app.services.document_registry import DocumentRegistry
from app.services.storage import JsonFileStore


def _mem_ids(registry: DocumentRegistry) -> set[str]:
    return {d.document_id for d in registry.list_all_documents()}


def _disk_ids(path: Path) -> set[str]:
    return {item["document_id"] for item in JsonFileStore.load(path, default=[])}


def main() -> int:
    """Run the register() failure-atomicity regression test."""
    print("=" * 60)
    print("register() Failure Atomicity Regression Test")
    print("=" * 60)

    checks = {"failed": False}

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        if not passed:
            checks["failed"] = True

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        registry_path = tmp / "documents.json"

        # 1. Normal registration keeps memory and disk in sync.
        registry = DocumentRegistry(registry_path)
        repo = JsonDocumentRepository(registry)
        repo.register("default", "a.pdf", 3, "user-a", document_id="doc-1")
        check(
            "normal register persists to memory and disk",
            _mem_ids(registry) == {"doc-1"} and _disk_ids(registry_path) == {"doc-1"},
            f"mem={sorted(_mem_ids(registry))} disk={sorted(_disk_ids(registry_path))}",
        )
        check(
            "normal register is visible to a fresh instance",
            _mem_ids(DocumentRegistry(registry_path)) == {"doc-1"},
        )

        # 2. Save failure during register() rolls back the in-memory document.
        with mock.patch.object(
            JsonFileStore, "save", side_effect=OSError("simulated save failure")
        ):
            raised = False
            try:
                repo.register("default", "b.pdf", 2, "user-a", document_id="doc-2")
            except OSError:
                raised = True
        check("exception is still raised when save fails", raised is True)
        check(
            "new document removed from in-memory registry",
            "doc-2" not in _mem_ids(registry),
            str(sorted(_mem_ids(registry))),
        )
        check(
            "previously persisted document still in memory",
            _mem_ids(registry) == {"doc-1"},
            str(sorted(_mem_ids(registry))),
        )
        check(
            "previously persisted document unchanged on disk",
            _disk_ids(registry_path) == {"doc-1"},
            str(sorted(_disk_ids(registry_path))),
        )
        check(
            "fresh instance sees only the previously persisted documents",
            _mem_ids(DocumentRegistry(registry_path)) == {"doc-1"},
        )

        # 3. The registry remains usable after a failed register.
        repo.register("default", "c.pdf", 1, "user-a", document_id="doc-3")
        check(
            "registry remains usable after a failed register",
            _mem_ids(registry) == {"doc-1", "doc-3"}
            and _disk_ids(registry_path) == {"doc-1", "doc-3"},
            str(sorted(_mem_ids(registry))),
        )

        # 4. PostgreSQL backend behavior unchanged.
        engine = create_engine(f"sqlite:///{(tmp / 'pg.db').as_posix()}")
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        pg_repo = PostgresDocumentRepository(session_factory)
        pg_repo.register("default", "a.pdf", 3, "user-a", document_id="doc-1")
        check(
            "postgres register persists",
            len(pg_repo.list_all_documents()) == 1,
        )
        with mock.patch.object(
            Session, "commit", side_effect=RuntimeError("simulated commit failure")
        ):
            raised_pg = False
            try:
                pg_repo.register("default", "b.pdf", 2, "user-a", document_id="doc-2")
            except RuntimeError:
                raised_pg = True
        check("postgres register raises when commit fails", raised_pg is True)
        check(
            "postgres leaves no ghost after a failed commit",
            [d.document_id for d in pg_repo.list_all_documents()] == ["doc-1"],
        )
        engine.dispose()

    print("\n" + "=" * 60)
    print(
        "register() Failure Atomicity Regression Test "
        + ("PASSED" if not checks["failed"] else "FAILED")
    )
    print("=" * 60)
    return 1 if checks["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())