from dataclasses import dataclass


@dataclass(frozen=True)
class RAGPrompt:
    """A prompt plus the source metadata used to build it.

    Attributes:
        text: The formatted prompt text sent to the LLM.
        sources: Source metadata (e.g. filename and chunk id) for the
            retrieved chunks, kept separate from the prompt text.
    """

    text: str
    sources: list[dict]


class PromptBuilder:
    """Build prompts for question-answering from retrieved contexts."""

    def build_prompt(
        self,
        question: str,
        contexts: list[dict],
        history: list[dict[str, str]] | None = None,
    ) -> RAGPrompt:
        """Build a prompt from the retrieved contexts and conversation history.

        Args:
            question: The user's question.
            contexts: A list of retrieved context documents, each with
                ``text``, ``filename``, and ``chunk_id``.
            history: Optional prior messages (``{"role", "content"}``) to
                prepend before the current question.

        Returns:
            A RAGPrompt containing the formatted prompt text and the source
            metadata of the retrieved chunks.
        """
        context_texts = [context["text"] for context in contexts]
        context_block = "\n\n------------------\n\n".join(context_texts)
        history_block = self._format_history(history)
        text = (
            "You are a helpful AI assistant.\n\n"
            "Answer the question using the provided context and conversation "
            "history when they contain the answer.\n\n"
            "Base every claim about the uploaded documents strictly on the "
            "provided context. Do not invent or guess facts about the "
            "documents.\n\n"
            "If the context genuinely does not contain enough information to "
            "answer the question, reply:\n\n"
            '"I couldn\'t find that information in the uploaded documents."\n\n'
            "Context:\n\n"
            f"{context_block}\n\n"
            f"{history_block}"
            "Question:\n\n"
            f"{question}\n\n"
            "Answer:"
        )
        sources = [
            {"filename": context["filename"], "chunk_id": context["chunk_id"]}
            for context in contexts
        ]
        return RAGPrompt(text=text, sources=sources)

    def build_general_prompt(self, question: str) -> RAGPrompt:
        """Build a plain conversational prompt without document context.

        Used for general queries that do not need document retrieval. Sources
        are empty because no document context is provided.

        Args:
            question: The user's question.

        Returns:
            A RAGPrompt containing the plain prompt and no sources.
        """
        text = (
            "You are a helpful AI assistant.\n\n"
            "Answer the user's question based on your general knowledge. If "
            "you do not know the answer, say so rather than guessing.\n\n"
            "Question:\n\n"
            f"{question}\n\n"
            "Answer:"
        )
        return RAGPrompt(text=text, sources=[])

    @staticmethod
    def _format_history(history: list[dict[str, str]] | None) -> str:
        """Format prior conversation messages for the prompt.

        Args:
            history: A list of messages (`` {"role", "content"}``), or None.

        Returns:
            A string of the formatted history, or an empty string if there is
            no history.
        """
        if not history:
            return ""
        lines = []
        for message in history:
            role = "User" if message["role"] == "user" else "Assistant"
            lines.append(f"{role}: {message['content']}")
        return "Conversation history:\n\n" + "\n".join(lines) + "\n\n"