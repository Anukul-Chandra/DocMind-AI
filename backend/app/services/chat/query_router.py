"""Hybrid relevance-gated query classification into routing categories.

Classification is deterministic for the two closed intents and hybrid for
everything else, in this order:

1. Metadata intent (document list/count) with token-level fuzzy matching so
   typos such as "dcuments"/"uploadd" still resolve. Routed to METADATA with
   no retrieval and no LLM call.
2. Explicit document filename references (``.pdf``/``.docx``/``.txt`` and
   similar). Routed to DOCUMENT.
3. Relevance gate combining the owner-scoped semantic similarity (MiniLM
   cosine) with owner-scoped BM25 lexical evidence and lightweight query
   signals (personal reference, self-attribute, explicit document noun):

   - self-referential questions ("my CV", "where did I study?") may use the
     low ``rag_personal_floor``;
   - questions naming a document noun ("paper", "document", "file") may use
     ``rag_docnoun_floor`` when combined with positive BM25 evidence;
   - generic topical questions (no personal reference, no document noun)
     require the high ``rag_topic_threshold``;
   - otherwise GENERAL.

No LLM call is ever made for classification. The semantic and lexical
scorers are injected (in production the shared ``SemanticRetriever`` and
``BM25Retriever``), so this class stays small and knows nothing about FAISS,
metadata stores, or document registries. When no scorer is injected,
classification degrades to the deterministic rules and everything else is
GENERAL.
"""

from enum import Enum
import re

from app.core.config import settings
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
#: *collection* (list/count) rather than document content. Exact matches on
#: normalized text; typo variants are handled separately by edit distance.
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
    "what files",
    "which files",
    "how many files",
    "list my files",
    "list the files",
)

#: Keywords whose typo variants (edit distance <= 1) still count as the
#: keyword for metadata intent detection.
_METADATA_KEYWORDS: tuple[str, ...] = ("documents", "upload", "files")

#: Trigger words that, together with a document/upload keyword, mark a
#: metadata intent (a question about the document list rather than content).
_METADATA_TRIGGERS: tuple[str, ...] = (
    "how many",
    "what",
    "which",
    "list",
    "do i have",
    "have i",
    "did i",
    "uploaded",
    "upload",
    "my documents",
    "my files",
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

#: Explicit document nouns that force (or rescue) the document path when the
#: user names a specific document rather than referring to it implicitly.
_DOCUMENT_NOUNS: tuple[str, ...] = (
    "paper",
    "document",
    "doc",
    "file",
    "pdf",
    "report",
)

#: Words that signal the user is asking about their own documents (first
#: person / possessive) rather than about a general topic. "mi" is the common
#: typo of "my" ("summarize mi resume plz").
_PERSONAL_REFERENCE: tuple[str, ...] = (
    "my",
    "mi",
    "mine",
    "i",
    "me",
    "myself",
    "our",
    "ours",
)

#: Self-attribute keywords: facts that commonly live in a user's own
#: documents (resume/CV/papers). Combined with personal reference these mark
#: an implicit question about the user's own data.
_SELF_ATTRIBUTES: tuple[str, ...] = (
    "cv",
    "resume",
    "education",
    "study",
    "studied",
    "university",
    "degree",
    "live",
    "living",
    "address",
    "phone",
    "phone number",
    "number",
    "email",
    "job",
    "work",
    "experience",
    "skills",
    "skill",
    "project",
    "projects",
    "certification",
    "certifications",
    "name",
    "background",
    "professional background",
    "role",
    "position",
    "company",
    "employer",
)

#: Tokens treated as fuzzy-matchable in metadata detection.
_METADATA_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

_MAX_EDIT_DISTANCE = 1


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenization for fuzzy metadata matching."""
    return _METADATA_TOKEN_PATTERN.findall(text.lower())


def _edit_distance(a: str, b: str) -> int:
    """Return the Levenshtein edit distance between two short strings.

    Args:
        a: The first string.
        b: The second string.

    Returns:
        The minimum number of single-character insertions, deletions, or
        substitutions needed to turn ``a`` into ``b``.
    """
    if a == b:
        return 0
    if len(a) == 0:
        return len(b)
    if len(b) == 0:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(
                min(
                    current[j - 1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + cost,
                )
            )
        previous = current
    return previous[-1]


class QueryRouter:
    """Classify a chat query into a routing category.

    Deterministic rules (metadata intent, explicit filename) run first and
    always win. Questions that match no pattern are scored against the user's
    own indexed corpus through the injected semantic and lexical scorers using
    the audited hybrid rule; only the resulting decision routes to document
    retrieval.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        relevance_scorer=None,
        lexical_scorer=None,
        relevance_threshold: float | None = None,
        personal_floor: float | None = None,
        topic_threshold: float | None = None,
        docnoun_floor: float | None = None,
    ) -> None:
        """Initialize the router with optional scorers and thresholds.

        Args:
            embedding_service: Optional ``EmbeddingService`` used to embed the
                question for the relevance gate so the same embedding can be
                reused for retrieval. When None, the gate is skipped.
            relevance_scorer: Optional callable ``(question, owner_id,
                query_embedding) -> float`` returning the best cosine
                similarity of the question against the user's eligible corpus
                chunks. When None, classification is purely deterministic.
            lexical_scorer: Optional callable ``(question, owner_id) ->
                float`` returning the best owner-scoped BM25 score. When None,
                the document-noun rescue branch is disabled.
            relevance_threshold: Deprecated single-threshold fallback, kept
                for callers that do not use the hybrid rule. Defaults to
                ``settings.rag_relevance_threshold``.
            personal_floor: Minimum cosine similarity for self-referential
                questions. Defaults to ``settings.rag_personal_floor``.
            topic_threshold: Minimum cosine similarity for generic topical
                questions. Defaults to ``settings.rag_topic_threshold``.
            docnoun_floor: Minimum cosine similarity for questions that name a
                document noun (combined with BM25 evidence).
                Defaults to ``settings.rag_docnoun_floor``.
        """
        self._embedding_service = embedding_service
        self._relevance_scorer = relevance_scorer
        self._lexical_scorer = lexical_scorer
        if relevance_threshold is None:
            relevance_threshold = settings.rag_relevance_threshold
        self._relevance_threshold = relevance_threshold
        if personal_floor is None:
            personal_floor = settings.rag_personal_floor
        if topic_threshold is None:
            topic_threshold = settings.rag_topic_threshold
        if docnoun_floor is None:
            docnoun_floor = settings.rag_docnoun_floor
        self._personal_floor = personal_floor
        self._topic_threshold = topic_threshold
        self._docnoun_floor = docnoun_floor
        self.last_query_embedding: list[float] | None = None

    def classify(self, question: str, owner_id: str = "") -> QueryCategory:
        """Return the routing category for the given question.

        Deterministic rules take precedence. Only when they do not match is the
        question embedded and scored against the user's own corpus; below the
        relevance thresholds the question remains GENERAL.

        Args:
            question: The user's chat question.
            owner_id: The user id whose corpus determines relevance. Empty for
                the legacy ownerless path.

        Returns:
            The routing category for the question.
        """
        text = question.strip().lower()
        if self._is_metadata_intent(text):
            return QueryCategory.METADATA
        if _DOCUMENT_EXTENSION_PATTERN.search(text):
            return QueryCategory.DOCUMENT
        if self._embedding_service is None or self._relevance_scorer is None:
            return QueryCategory.GENERAL
        return self._classify_relevance(question, owner_id, text)

    @staticmethod
    def _is_metadata_intent(text: str) -> bool:
        """Return whether the question asks about the document list/count.

        Matches exact metadata patterns first; then falls back to token-level
        fuzzy matching so typo variants ("dcuments", "documnts", "uploadd")
        still resolve to METADATA without consulting retrieval or an LLM.

        Args:
            text: The lowercased question text.

        Returns:
            True if the question is a metadata request.
        """
        if any(pattern in text for pattern in _METADATA_PATTERNS):
            return True
        tokens = _tokenize(text)
        has_keyword = False
        for token in tokens:
            for keyword in _METADATA_KEYWORDS:
                if abs(len(token) - len(keyword)) > _MAX_EDIT_DISTANCE + 1:
                    continue
                if _edit_distance(token, keyword) <= _MAX_EDIT_DISTANCE:
                    has_keyword = True
                    break
            if has_keyword:
                break
        if not has_keyword:
            return False
        return any(trigger in text for trigger in _METADATA_TRIGGERS)

    def _classify_relevance(self, question: str, owner_id: str, text: str) -> QueryCategory:
        """Embed once, combine signals, and route by the audited rule."""
        query_embedding = self._embedding_service.generate_embeddings([question])[0]
        self.last_query_embedding = query_embedding
        similarity = self._relevance_scorer(
            question,
            owner_id,
            query_embedding,
        )
        lexical = 0.0
        if self._lexical_scorer is not None:
            lexical = self._lexical_scorer(question, owner_id)
        personal = self._has_personal_reference(text)
        docnoun = self._has_document_noun(text)
        self_attribute = self._has_self_attribute(text)

        if personal and self_attribute:
            if similarity >= self._personal_floor:
                return QueryCategory.DOCUMENT
        elif personal:
            if similarity >= self._personal_floor and lexical > 0.0:
                return QueryCategory.DOCUMENT
        if docnoun and lexical > 0.0 and similarity >= self._docnoun_floor:
            return QueryCategory.DOCUMENT
        if similarity >= self._topic_threshold:
            return QueryCategory.DOCUMENT
        return QueryCategory.GENERAL

    @staticmethod
    def _has_personal_reference(text: str) -> bool:
        """Return whether the question refers to the user themselves."""
        for token in _tokenize(text):
            if token in _PERSONAL_REFERENCE:
                return True
        return False

    @staticmethod
    def _has_document_noun(text: str) -> bool:
        """Return whether the question names an explicit document noun."""
        for noun in _DOCUMENT_NOUNS:
            if noun in text:
                return True
        return False

    @staticmethod
    def _has_self_attribute(text: str) -> bool:
        """Return whether the question asks about a personal self-attribute."""
        for attribute in _SELF_ATTRIBUTES:
            if attribute in text:
                return True
        return False
