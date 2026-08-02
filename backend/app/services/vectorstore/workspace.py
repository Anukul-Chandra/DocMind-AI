"""Workspace grouping for indexed documents."""

from dataclasses import dataclass


DEFAULT_WORKSPACE = "default"
DEFAULT_WORKSPACE_NAME = "Default"


@dataclass(frozen=True)
class Workspace:
    """A named group that owns indexed documents.

    Attributes:
        workspace_id: A stable identifier for the workspace.
        name: A human-readable name for the workspace.
    """

    workspace_id: str
    name: str


class WorkspaceStore:
    """In-memory registry of workspaces.

    All data lives in memory only, so this registry resets when the server
    restarts. No database persistence.
    """

    def __init__(self) -> None:
        """Initialize an empty workspace registry."""
        self._workspaces: dict[str, Workspace] = {}

    def get_or_create(self, name: str) -> Workspace:
        """Return the workspace with the given name, creating it if needed.

        Args:
            name: The workspace name, also used as its identifier.

        Returns:
            The matching workspace.
        """
        workspace = self._workspaces.get(name)
        if workspace is None:
            workspace = Workspace(workspace_id=name, name=name)
            self._workspaces[name] = workspace
        return workspace

    def default(self) -> Workspace:
        """Return the default workspace, creating it if needed.

        Returns:
            The default workspace.
        """
        return self.get_or_create(DEFAULT_WORKSPACE)