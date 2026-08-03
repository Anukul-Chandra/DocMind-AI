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
        document_id: str | None = None,
    ) -> Document:
        """Register a new indexed document.

        Args:
            workspace_id: The workspace the document belongs to.
            filename: The original document filename.
            chunk_count: The number of chunks indexed for the document.
            document_id: An explicit identifier, or None to generate one.

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
            row = db.Document(
                id=document_id,
                workspace_id=workspace_id,
                filename=filename,
                uploaded_at=now,
                chunk_count=chunk_count,
                deleted=False,
            )
            session.add(row)
        return Document(
            document_id=document_id,
            workspace_id=workspace_id,
            filename=filename,
            uploaded_at=now,
            chunk_count=chunk_count,
        )

    def list_documents(self) -> list[Document]:
        """Return all registered documents.

        Returns:
            A list of all tracked documents.
        """
        with self._session_factory() as session:
            rows = session.execute(select(db.Document)).scalars().all()
        return [self._to_domain(row) for row in rows]

    def get_document(self, document_id: str) -> Document | None:
        """Return a document by its identifier.

        Args:
            document_id: The document identifier.

        Returns:
            The matching document, or None if it is not known.
        """
        with self._session_factory() as session:
            row = session.get(db.Document, document_id)
        return self._to_domain(row) if row is not None else None

    def exists(self, document_id: str) -> bool:
        """Return whether a document identifier is registered.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document exists in the repository.
        """
        with self._session_factory() as session:
            return session.get(db.Document, document_id) is not None

    def delete_document(self, document_id: str) -> bool:
        """Mark a document as deleted.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document was found and marked deleted.
        """
        with self._session_factory() as session:
            row = session.get(db.Document, document_id)
            if row is None or row.deleted:
                return False
            row.deleted = True
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
        )
