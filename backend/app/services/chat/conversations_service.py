"""Ownership-guarded service for chat conversation history."""

from app.repositories.interfaces import ConversationRepository
from app.services.chat_domain import ConversationMessage, ConversationMeta


class ConversationNotFoundError(Exception):
    """Raised when a conversation is unknown or belongs to another owner."""


class ConversationsService:
    """Provide ownership-scoped operations over chat conversations.

    This service is a thin layer over :class:`ConversationRepository` that adds
    explicit ownership. Every call takes an ``owner_id`` (the authenticated
    user) and maps a missing or cross-user conversation to a
    :class:`ConversationNotFoundError`, so route handlers can translate it to a
    404 without leaking whether the conversation exists for another user.
    """

    def __init__(self, repository: ConversationRepository) -> None:
        """Initialize the service with a conversation repository.

        Args:
            repository: The conversation repository (JSON or PostgreSQL).
        """
        self._repository = repository

    def create(self, owner_id: str) -> ConversationMeta:
        """Create a new empty conversation owned by a user.

        Args:
            owner_id: The user id that owns the conversation.

        Returns:
            The created conversation metadata.
        """
        conversation_id = self._repository.create_conversation(owner_id)
        meta = self._repository.get_conversation(conversation_id, owner_id)
        if meta is None:  # pragma: no cover - defender for non-returning repos
            meta = ConversationMeta(
                conversation_id=conversation_id, owner_id=owner_id
            )
        return meta

    def list_for_user(self, owner_id: str) -> list[ConversationMeta]:
        """Return all conversations owned by a user, newest first.

        Args:
            owner_id: The user id whose conversations to return.

        Returns:
            A list of conversation summaries owned by the user.
        """
        return self._repository.list_conversations(owner_id)

    def get(self, conversation_id: str, owner_id: str) -> ConversationMeta:
        """Return a conversation if it belongs to the owner.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            The matching conversation metadata.

        Raises:
            ConversationNotFoundError: If the conversation is unknown or
                belongs to another owner.
        """
        meta = self._repository.get_conversation(conversation_id, owner_id)
        if meta is None:
            raise ConversationNotFoundError(conversation_id)
        return meta

    def get_messages(
        self, conversation_id: str, owner_id: str
    ) -> list[ConversationMessage]:
        """Return the messages for a conversation if owned by the caller.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            The conversation's messages.

        Raises:
            ConversationNotFoundError: If the conversation is unknown or
                belongs to another owner.
        """
        meta = self._repository.get_conversation(conversation_id, owner_id)
        if meta is None:
            raise ConversationNotFoundError(conversation_id)
        return self._repository.get_messages(conversation_id, owner_id)

    def rename(self, conversation_id: str, owner_id: str, title: str) -> ConversationMeta:
        """Rename a conversation if it belongs to the owner.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.
            title: The new conversation title.

        Returns:
            The updated conversation metadata.

        Raises:
            ConversationNotFoundError: If the conversation is unknown or
                belongs to another owner.
        """
        if not title or not title.strip():
            title = "Untitled"
        renamed = self._repository.rename_conversation(
            conversation_id, owner_id, title.strip()
        )
        if not renamed:
            raise ConversationNotFoundError(conversation_id)
        return self.get(conversation_id, owner_id)

    def delete(self, conversation_id: str, owner_id: str) -> None:
        """Delete a conversation if owned by the caller.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Raises:
            ConversationNotFoundError: If the conversation is unknown or
                belongs to another owner.
        """
        if not self._repository.delete_conversation(conversation_id, owner_id):
            raise ConversationNotFoundError(conversation_id)
