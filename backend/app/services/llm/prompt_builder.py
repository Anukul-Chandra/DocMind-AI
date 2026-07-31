class PromptBuilder:
    """Build prompts for question-answering from retrieved contexts."""

    def build_prompt(self, question: str, contexts: list[dict]) -> str:
        """Build a prompt using only the text from each provided context.

        Args:
            question: The user's question.
            contexts: A list of retrieved context documents.

        Returns:
            A formatted prompt string.
        """
        context_texts = [context["text"] for context in contexts]
        context_block = "\n\n------------------\n\n".join(context_texts)
        return (
            "You are a helpful AI assistant.\n\n"
            "Answer ONLY using the provided context.\n\n"
            "If the answer is not available in the context,\n"
            'reply:\n\n"I couldn\'t find that information in the uploaded documents."\n\n'
            "Context:\n\n"
            f"{context_block}\n\n"
            "Question:\n\n"
            f"{question}\n\n"
            "Answer:"
        )
