"""In-memory conversation memory for the chat pipeline."""

import uuid

#: Maximum number of message pairs kept per conversation.
CONVERSATION_LIMIT = 10


class ConversationMemory:
    """Store recent conversation history in memory.

    Each conversation is identified by a ``conversation_id`` and keeps a
    bounded sliding window of the most recent user/assistant message pairs.
    All data lives in-process only, so memory naturally resets on server
    restart. No Redis, no database.
    """

    def __init__(self) -> None:
        """Initialize an empty conversation store."""
        self._conversations: dict[str, list[dict[str, str]]] = {}

    def create_conversation(self) -> str:
        """Create a new empty conversation and return its identifier.

        Returns:
            A UUID string identifying the new conversation.
        """
        conversation_id = str(uuid.uuid4())
        self._conversations[conversation_id] = []
        return conversation_id

    def get_history(self, conversation_id: str) -> list[dict[str, str]]:
        """Return the stored message history for a conversation.

        Args:
            conversation_id: The conversation identifier.

        Returns:
            A list of messages (``{"role", "content"}``) for the conversation,
            or an empty list if the conversation is unknown.
        """
        return list(self._conversations.get(conversation_id, []))

    def add_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Record a user/assistant exchange, trimming to the latest pairs.

        Args:
            conversation_id: The conversation identifier.
            user_message: The user's question.
            assistant_response: The assistant's answer.
        """
        messages = self._conversations.setdefault(conversation_id, [])
        messages.append({"role": "user", "content": user_message})
        messages.append({"role": "assistant", "content": assistant_response})
        self._trim(messages)

    @staticmethod
    def _trim(messages: list[dict[str, str]]) -> None:
        """Keep only the most recent messages within the configured window.

        Args:
            messages: The message list to trim in place.
        """
        max_messages = CONVERSATION_LIMIT * 2
        if len(messages) > max_messages:
            del messages[: len(messages) - max_messages]