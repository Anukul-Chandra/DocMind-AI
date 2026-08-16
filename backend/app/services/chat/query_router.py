"""Hybrid query classification into routing categories.

Classification is deterministic string matching first, with a semantic
(embedding-based) fallback only when the deterministic pass would return
GENERAL:

1. Explicit document filename references (``.pdf``/``.docx``/``.txt`` and
   similar) are matched first.
2. Metadata requests (about the document list/count) are matched next.
3. Document-anchored phrases are matched next.
4. Only if none of the above matched (so the query would be GENERAL), the
   question is embedded with the reusable ``EmbeddingService`` and compared
   against cached per-category centroid embeddings of small seed phrase sets.

No LLM call is ever made for classification. When no ``EmbeddingService`` is
injected, the router degrades to the pure deterministic behavior.
"""

from enum import Enum
import re

import numpy as np

from app.services.embedding import EmbeddingService


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

#: Representative seed phrases per category for the semantic fallback. These
#: are embedded once and averaged into a centroid per category; a question
#: whose embedding is closest to a centroid (above the threshold) is routed to
#: that category.
_METADATA_SEEDS: tuple[str, ...] = (
    "which documents have i uploaded",
    "how many documents do i have",
    "how many documents have i uploaded",
    "list my documents",
    "which documents do i have",
    "what documents did i upload",
    "list the documents i uploaded",
    "what documents are in my account",
)

_DOCUMENT_SEEDS: tuple[str, ...] = (
    "what is in my cv",
    "what is in my resume",
    "summarize my cv",
    "summarize my resume",
    "based on my resume what roles suit me",
    "what is the main topic of my documents",
    "what does my pdf say about my skills",
    "what education does my cv mention",
)

_GENERAL_SEEDS: tuple[str, ...] = (
    "hello",
    "how are you",
    "what is rag",
    "explain machine learning",
    "tell me a joke",
    "what is the capital of france",
)

#: Minimum cosine similarity for the semantic fallback to override GENERAL.
#: Below this the question is treated as GENERAL. Chosen conservatively so
#: genuinely unrelated chatter is not routed to document or metadata paths.
_SIMILARITY_THRESHOLD = 0.35


class QueryRouter:
    """Classify a chat query into a routing category.

    Deterministic patterns run first and always win. The embedding-based
    semantic fallback is used only when the deterministic pass would return
    GENERAL. Centroid embeddings are computed lazily and cached so seeds are
    embedded once per process, not per query.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """Initialize the router with an optional embedding service.

        Args:
            embedding_service: Optional ``EmbeddingService`` used for the
                semantic fallback. When None, classification is purely
                deterministic.
        """
        self._embedding_service = embedding_service
        self._centroids: dict[QueryCategory, np.ndarray] | None = None

    def classify(self, question: str) -> QueryCategory:
        """Return the routing category for the given question.

        Deterministic rules take precedence. Only when they would return
        GENERAL is the embedding fallback consulted; below the similarity
        threshold the question remains GENERAL.

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
        if self._embedding_service is None:
            return QueryCategory.GENERAL
        return self._classify_semantic(text)

    def _classify_semantic(self, text: str) -> QueryCategory:
        """Classify via cosine similarity against cached category centroids."""
        query = np.asarray(
            self._embedding_service.generate_embeddings([text])[0],
            dtype=np.float64,
        )
        norm = float(np.linalg.norm(query))
        if norm == 0.0:
            return QueryCategory.GENERAL
        query = query / norm

        best_category = QueryCategory.GENERAL
        best_similarity = -1.0
        for category, centroid in self._get_centroids().items():
            centroid_norm = float(np.linalg.norm(centroid))
            if centroid_norm == 0.0:
                continue
            similarity = float(np.dot(query, centroid) / centroid_norm)
            if similarity > best_similarity:
                best_similarity = similarity
                best_category = category

        if best_similarity >= _SIMILARITY_THRESHOLD:
            return best_category
        return QueryCategory.GENERAL

    def _get_centroids(self) -> dict[QueryCategory, np.ndarray]:
        """Return per-category centroid embeddings, computing them once."""
        if self._centroids is None:
            seeds: dict[QueryCategory, tuple[str, ...]] = {
                QueryCategory.METADATA: _METADATA_SEEDS,
                QueryCategory.DOCUMENT: _DOCUMENT_SEEDS,
                QueryCategory.GENERAL: _GENERAL_SEEDS,
            }
            centroids: dict[QueryCategory, np.ndarray] = {}
            for category, phrases in seeds.items():
                vectors = np.asarray(
                    self._embedding_service.generate_embeddings(list(phrases)),
                    dtype=np.float64,
                )
                centroids[category] = vectors.mean(axis=0)
            self._centroids = centroids
        return self._centroids