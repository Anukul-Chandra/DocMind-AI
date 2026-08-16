"""Deterministic, lightweight classification of chat queries into routing categories.

Classification is pure substring matching over the lowercased question: no
LLM call is made to classify. Metadata requests are detected first, then
document-anchored questions, and everything else is treated as general chat.
"""

from enum import Enum


class QueryCategory(Enum):
    """The routing category for a chat query.

    Attributes:
        GENERAL: General conversation; no document retrieval.
        DOCUMENT: Document-grounded or mixed question; uses retrieval + the
            grounded prompt flow.
        METADATA: A request about the user's document list/count; no retrieval
            and no LLM call.
    """

    GENERAL = "general"
    DOCUMENT = "document"
    METADATA = "metadata"


#: Lowercase substrings that signal a request about the user's document
#: *collection* (list/count) rather than document content.
_METADATA_PATTERNS: tuple[str, ...] = (
    "how many documents",
    "what documents",
    "which documents",
    "list of documents",
    "list my documents",
    "list the documents",
    "documents list",
    "documents do i have",
    "documents have i",
    "documents did i",
    "uploaded documents",
    "did i upload",
    "have i uploaded",
)

#: Lowercase substrings that anchor a question to the user's own uploaded
#: documents (personal possessives with document/content words, or phrases
#: such as "based on my"). Without such an anchor the question is general.
_DOCUMENT_PATTERNS: tuple[str, ...] = (
    "my cv",
    "my resume",
    "my documents",
    "my document",
    "my file",
    "my pdf",
    "my uploads",
    "my profile",
    "my education",
    "my skills",
    "my experience",
    "based on my",
    "according to my",
    "the cv",
    "the resume",
    "this document",
)


class QueryRouter:
    """Classify a chat query into a routing category.

    Categories are matched in order: metadata, then document, then general.
    The classification is deterministic and cheap so it can run on every
    request without an additional LLM call.
    """

    def classify(self, question: str) -> QueryCategory:
        """Return the routing category for the given question.

        Args:
            question: The user's chat question.

        Returns:
            The routing category for the question.
        """
        text = question.strip().lower()
        if any(pattern in text for pattern in _METADATA_PATTERNS):
            return QueryCategory.METADATA
        if any(pattern in text for pattern in _DOCUMENT_PATTERNS):
            return QueryCategory.DOCUMENT
        return QueryCategory.GENERAL