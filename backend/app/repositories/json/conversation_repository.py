"""JSON-backed implementation of the ConversationRepository interface."""

from app.repositories.interfaces import ConversationRepository
from app.services.chat.memory import ConversationMemory


class JsonConversationRepository(ConversationRepository):
    """In-memory JSON conversation repository.

    Delegates to the existing :class:`ConversationMemory` so callers depend
    only on the :class:`ConversationRepository` interface.
    """

    def __init__(self, memory: ConversationMemory) -> None:
        """Initialize the repository with an in-memory conversation store.

        Args:
            memory: The backing conversation memory.
        """
        self._memory = memory

    def create_conversation(self) -> str:
        """Create a new empty conversation.

        Returns:
            An identifier for the new conversation.
        """
        return self._memory.create_conversation()

    def get_history(self, conversation_id: str) -> list[dict[str, str]]:
        """Return the stored message history for a conversation.

        Args:
            conversation_id: The conversation identifier.

        Returns:
            The message history, or an empty list if unknown.
        """
        return self._memory.get_history(conversation_id)

    def add_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Record a user/assistant exchange.

        Args:
            conversation_id: The conversation identifier.
            user_message: The user's question.
            assistant_response: The assistant's answer.
        """
        self._memory.add_exchange(
            conversation_id,
            user_message,
            assistant_response,
        )
