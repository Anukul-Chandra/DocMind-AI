"""PostgreSQL-backed implementation of the DocumentRepository interface."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import models as db
from app.db.session import SessionFactory
from app.repositories.interfaces import DocumentRepository
from app.services.document_registry import Document


class PostgresDocumentRepository(DocumentRepository):
    """PostgreSQL document repository.

    Maps the ``documents`` table to the domain :class:`Document` model while
    preserving the same behavioral contract as the JSON-backed implementation
    (including soft-deletion and unknown-document semantics).
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        """Initialize the repository with a session factory.

        Args:
            session_factory: A callable returning a fresh session per
                operation.
        """
        self._session_factory = session_factory

    def register(
        self,
        workspace_id: str,
        filename: str,
        chunk_count: int,
        owner_id: str,
        document_id: str | None = None,
        classification: str = "unknown",
    ) -> Document:
        """Register a new indexed document owned by a user.

        Args:
            workspace_id: The workspace the document belongs to.
            filename: The original document filename.
            chunk_count: The number of chunks indexed for the document.
            owner_id: The user id that owns the document.
            document_id: An explicit identifier, or None to generate one.
            classification: The document type, or ``unknown``. Accepted for
                interface compatibility but not persisted: the ``documents``
                table schema is out of scope, so documents read back through
                this backend report ``unknown``.

        Returns:
            The registered document.
        """
        document_id = document_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            workspace = session.get(db.Workspace, workspace_id)
            if workspace is None:
                session.add(
                    db.Workspace(id=workspace_id, name=workspace_id, created_at=now)
                )
                session.flush()
            row = db.Document(
                id=document_id,
                workspace_id=workspace_id,
                filename=filename,
                uploaded_at=now,
                chunk_count=chunk_count,
                owner_id=owner_id,
                deleted=False,
            )
            session.add(row)
            session.commit()
        return Document(
            document_id=document_id,
            workspace_id=workspace_id,
            filename=filename,
            uploaded_at=now,
            chunk_count=chunk_count,
            owner_id=owner_id,
        )

    def list_documents(self, owner_id: str) -> list[Document]:
        """Return all documents owned by a user.

        Args:
            owner_id: The user id whose documents to return.

        Returns:
            A list of documents owned by the given user.
        """
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(db.Document).where(db.Document.owner_id == owner_id)
                )
                .scalars()
                .all()
            )
        return [self._to_domain(row) for row in rows]

    def get_document(self, document_id: str, owner_id: str) -> Document | None:
        """Return a document by identifier if it belongs to the owner.

        Args:
            document_id: The document identifier.
            owner_id: The expected owner of the document.

        Returns:
            The matching document, or None if it is not known or belongs to
            another owner.
        """
        with self._session_factory() as session:
            row = session.execute(
                select(db.Document).where(
                    db.Document.id == document_id,
                    db.Document.owner_id == owner_id,
                )
            ).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    def list_all_documents(self) -> list[Document]:
        """Return every registered document regardless of owner.

        Returns:
            A list of every registered document.
        """
        with self._session_factory() as session:
            rows = session.scalars(select(db.Document)).all()
        return [self._to_domain(row) for row in rows]

    def exists(self, document_id: str) -> bool:
        """Return whether a document identifier is registered.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document exists in the repository.
        """
        with self._session_factory() as session:
            return session.get(db.Document, document_id) is not None

    def delete_document(self, document_id: str, owner_id: str) -> bool:
        """Mark a document as deleted if it belongs to the owner.

        Args:
            document_id: The document identifier.
            owner_id: The expected owner of the document.

        Returns:
            True if the document was found, owned by the caller, and marked
            deleted.
        """
        with self._session_factory() as session:
            row = session.execute(
                select(db.Document).where(
                    db.Document.id == document_id,
                    db.Document.owner_id == owner_id,
                )
            ).scalar_one_or_none()
            if row is None or row.deleted:
                return False
            row.deleted = True
            session.commit()
            return True

    def is_deleted(self, document_id: str) -> bool:
        """Return whether a document is marked deleted.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document is marked deleted; unknown documents are
            treated as not deleted, matching the JSON-backed implementation.
        """
        with self._session_factory() as session:
            row = session.get(db.Document, document_id)
        return bool(row and row.deleted)

    @staticmethod
    def _to_domain(row: db.Document) -> Document:
        """Convert a document row to the domain model.

        Args:
            row: The database document row.

        Returns:
            The domain :class:`Document`.
        """
        return Document(
            document_id=row.id,
            workspace_id=row.workspace_id,
            filename=row.filename,
            uploaded_at=row.uploaded_at,
            chunk_count=row.chunk_count,
            deleted=row.deleted,
            owner_id=row.owner_id,
        )
