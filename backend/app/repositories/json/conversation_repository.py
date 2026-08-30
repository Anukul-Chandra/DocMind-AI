"""JSON-backed implementation of the ConversationRepository interface."""

from app.repositories.interfaces import ConversationRepository
from app.services.chat_domain import ConversationMessage, ConversationMeta
from app.services.chat.memory import ConversationMemory


class JsonConversationRepository(ConversationRepository):
    """File-backed JSON conversation repository.

    Delegates to the existing :class:`ConversationMemory` so callers depend
    only on the :class:`ConversationRepository` interface. History persists to
    the JSON file owned by the memory instance and is scoped per user.
    """

    def __init__(self, memory: ConversationMemory) -> None:
        """Initialize the repository with a JSON conversation store.

        Args:
            memory: The backing conversation memory.
        """
        self._memory = memory

    def create_conversation(self, owner_id: str) -> str:
        """Create a new empty conversation owned by a user.

        Args:
            owner_id: The user id that owns the conversation.

        Returns:
            An identifier for the new conversation.
        """
        return self._memory.create_conversation(owner_id)

    def list_conversations(self, owner_id: str) -> list[ConversationMeta]:
        """Return all conversations owned by a user, newest first.

        Args:
            owner_id: The user id whose conversations to return.

        Returns:
            A list of conversation summaries owned by the user.
        """
        return self._memory.list_conversations(owner_id)

    def get_conversation(
        self, conversation_id: str, owner_id: str
    ) -> ConversationMeta | None:
        """Return a conversation if it belongs to the owner.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            The matching conversation metadata, or None if it is unknown or
            belongs to another owner.
        """
        return self._memory.get_conversation(conversation_id, owner_id)

    def get_messages(
        self, conversation_id: str, owner_id: str
    ) -> list[ConversationMessage]:
        """Return the messages for a conversation if owned by the caller.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            The conversation's messages, or an empty list if the conversation
            is unknown or belongs to another owner.
        """
        return self._memory.get_messages(conversation_id, owner_id)

    def add_exchange(
        self,
        conversation_id: str,
        owner_id: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Record a user/assistant exchange in a conversation.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The user id that owns the conversation.
            user_message: The user's question.
            assistant_response: The assistant's answer.
        """
        self._memory.add_exchange(
            conversation_id,
            owner_id,
            user_message,
            assistant_response,
        )

    def rename_conversation(
        self, conversation_id: str, owner_id: str, title: str
    ) -> bool:
        """Rename a conversation if it belongs to the owner.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.
            title: The new conversation title.

        Returns:
            True if the conversation was found, owned by the caller, and
            renamed.
        """
        return self._memory.rename_conversation(conversation_id, owner_id, title)

    def delete_conversation(self, conversation_id: str, owner_id: str) -> bool:
        """Delete a conversation if owned by the caller.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            True if the conversation was found, owned by the caller, and
            deleted.
        """
        return self._memory.delete_conversation(conversation_id, owner_id)
