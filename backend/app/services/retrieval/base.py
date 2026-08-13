from abc import ABC, abstractmethod

from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


class Retriever(ABC):
    """Abstract interface for retrieving relevant document chunks.

    ChatService depends only on this interface. Concrete implementations may
    retrieve using semantic (vector/FAISS), keyword (BM25), or a hybrid of both
    without the caller knowing which technique is used.
    """

    @abstractmethod
    def retrieve(
        self,
        query: str,
        k: int = 5,
        workspace_id: str = DEFAULT_WORKSPACE,
        owner_id: str = "",
    ) -> list[dict]:
        """Retrieve the most relevant document chunks for a query.

        Args:
            query: The search query text.
            k: The number of chunks to return.
            workspace_id: Only chunks belonging to this workspace are returned.
            owner_id: Only chunks owned by this user are returned. Empty for
                legacy chunks indexed before ownership was tracked.

        Returns:
            A list of matching document-chunk metadata dicts, ordered by
            relevance (best first), constrained to the workspace and owner.
        """

    @abstractmethod
    def is_eligible(
        self,
        document: dict,
        workspace_id: str,
        owner_id: str = "",
    ) -> bool:
        """Return whether a chunk is eligible for a workspace and owner.

        Args:
            document: The chunk metadata to check.
            workspace_id: The requested workspace.
            owner_id: The requested owner. Empty for legacy ownerless chunks.

        Returns:
            True if the chunk belongs to the workspace and owner and its
            owning document is not deleted; False otherwise.
        """