"""Deterministic, lightweight classification of chat queries into routing categories.

Classification is pure string matching over the lowercased question: no
LLM call is made to classify. Explicit document filename references
(``.pdf``/``.docx``/``.txt`` and similar) are matched first, then metadata
requests, then document-anchored phrases, and everything else is treated as
general chat.
"""

from enum import Enum
import re


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
    "the document",
    "this file",
    "that file",
    "the file",
)

#: Document file extensions that mark an explicit filename reference.
_DOCUMENT_EXTENSIONS: tuple[str, ...] = (
    "pdf",
    "docx",
    "doc",
    "txt",
    "md",
    "csv",
)

#: Matches a filename token (letters, digits, dots, plus, hyphen) ending in a
#: document extension, e.g. ``"Anukul-chandra Cv.pdf"`` -> ``cv.pdf``. A word
#: boundary handles trailing punctuation such as ``"notes.txt?"``.
_DOCUMENT_EXTENSION_PATTERN = re.compile(
    r"[\w.+-]+\.(?:{})\b".format("|".join(_DOCUMENT_EXTENSIONS))
)


class QueryRouter:
    """Classify a chat query into a routing category.

    Categories are matched in order: metadata, then document, then general.
    The classification is deterministic and cheap so it can run on every
    request without an additional LLM call.
    """

    def classify(self, question: str) -> QueryCategory:
        """Return the routing category for the given question.

        An explicit document filename reference (e.g. ``"Cv.pdf"``) is the
        strongest signal and is matched first. Metadata requests are detected
        next, then document-anchored phrases, and everything else is treated
        as general chat.

        Args:
            question: The user's chat question.

        Returns:
            The routing category for the question.
        """
        text = question.strip().lower()
        if _DOCUMENT_EXTENSION_PATTERN.search(text):
            return QueryCategory.DOCUMENT
        if any(pattern in text for pattern in _METADATA_PATTERNS):
            return QueryCategory.METADATA
        if any(pattern in text for pattern in _DOCUMENT_PATTERNS):
            return QueryCategory.DOCUMENT
        return QueryCategory.GENERAL