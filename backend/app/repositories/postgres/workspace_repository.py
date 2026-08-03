"""PostgreSQL-backed implementation of the WorkspaceRepository interface."""

from sqlalchemy import select

from app.db import models as db
from app.db.session import SessionFactory
from app.repositories.interfaces import WorkspaceRepository


class PostgresWorkspaceRepository(WorkspaceRepository):
    """PostgreSQL workspace repository.

    Unlike the JSON implementation (which derives workspaces from registered
    documents), this reads the dedicated ``workspaces`` table.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        """Initialize the repository with a session factory.

        Args:
            session_factory: A callable returning a fresh session per
                operation.
        """
        self._session_factory = session_factory

    def list_workspaces(self) -> list[str]:
        """Return all known workspace identifiers.

        Returns:
            A sorted list of distinct workspace identifiers.
        """
        with self._session_factory() as session:
            rows = session.execute(select(db.Workspace.id)).scalars().all()
        return sorted(rows)
