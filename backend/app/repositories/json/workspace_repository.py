"""JSON-backed implementation of the WorkspaceRepository interface."""

from app.repositories.interfaces import DocumentRepository, WorkspaceRepository


class JsonWorkspaceRepository(WorkspaceRepository):
    """JSON-backed workspace repository.

    Workspaces are not stored explicitly; they are derived from the distinct
    ``workspace_id`` values across all registered documents.
    """

    def __init__(self, document_repository: DocumentRepository) -> None:
        """Initialize the repository with a document repository.

        Args:
            document_repository: The source of document records.
        """
        self._documents = document_repository

    def list_workspaces(self) -> list[str]:
        """Return all known workspace identifiers.

        Returns:
            A sorted list of distinct workspace identifiers.
        """
        workspaces = {
            document.workspace_id
            for document in self._documents.list_documents()
        }
        return sorted(workspaces)
