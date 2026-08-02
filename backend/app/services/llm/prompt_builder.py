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

    def build_prompt(self, question: str, contexts: list[dict]) -> RAGPrompt:
        """Build a prompt from the retrieved contexts, keeping sources separate.

        Args:
            question: The user's question.
            contexts: A list of retrieved context documents, each with an
                ``id``, ``text``, and ``filename``.

        Returns:
            A RAGPrompt containing the formatted prompt text and the source
            metadata of the retrieved chunks.
        """
        context_texts = [context["text"] for context in contexts]
        context_block = "\n\n------------------\n\n".join(context_texts)
        text = (
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
        sources = [
            {"filename": context["filename"], "chunk_id": context["id"]}
            for context in contexts
        ]
        return RAGPrompt(text=text, sources=sources)