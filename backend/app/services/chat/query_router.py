"""Hybrid relevance-gated query classification into routing categories.

Classification is deterministic for the two closed intents and hybrid for
everything else, in this order:

1. Metadata intent (document list/count) with token-level fuzzy matching so
   typos such as "dcuments"/"uploadd" still resolve. Routed to METADATA with
   no retrieval and no LLM call. Questions framed as advice about future
   uploads ("which files should I upload?") are excluded here and stay
   GENERAL because they ask about files not yet in the collection.
2. Explicit document filename references (``.pdf``/``.docx``/``.txt`` and
   similar). Routed to DOCUMENT.
3. General-knowledge generation asks ("write a paper about machine learning",
   "explain machine learning", "create a report about AI") are routed to
   GENERAL unless they anchor to an existing document: a creation/explanation
   verb with a document noun as the *output* artifact (not a possessive,
   genitive, or definite reference to the user's own document) does not name
   an existing file.
4. Relevance gate combining the owner-scoped semantic similarity (MiniLM
   cosine) with owner-scoped BM25 lexical evidence and lightweight query
   signals (personal reference, self-attribute, explicit document noun):

   - self-referential questions ("my CV", "where did I study?") may use the
     low ``rag_personal_floor``; self-attributes are fuzzy-matched so typos
     ("universty") still resolve;
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

from dataclasses import dataclass
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


@dataclass
class RouteResult:
    """The outcome of classifying a single query.

    Attributes:
        category: The routing category for the query.
        query_embedding: The embedding generated from the *current* question
            when semantic retrieval is required (DOCUMENT category), otherwise
            ``None``. This is request-local: it is produced for exactly one
            classification call and never persisted on shared instance state,
            so a later query can never silently reuse a previous embedding.
    """

    category: QueryCategory
    query_embedding: list[float] | None = None


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

#: Creation verbs that frame the production of a new artifact. A document noun
#: following a creation verb is the artifact being written (an *output*), not
#: an existing document, so such questions are general-knowledge generation
#: asks unless the artifact is explicitly bound to a document the user owns
#: ("my paper", "a summary of my paper").
_CREATION_VERBS: tuple[str, ...] = (
    "write",
    "create",
    "generate",
    "compose",
    "produce",
    "draft",
    "prepare",
    "formulate",
    "outline",
)

#: Explanation / definition frames that ask the LLM to produce general
#: knowledge about a topic rather than interrogate an existing document.
_EXPLANATION_VERBS: tuple[str, ...] = (
    "explain",
    "define",
    "describe",
    "what is",
    "what are",
)

#: All frames that mark a general-knowledge generation ask.
_GENERAL_ASK_VERBS: tuple[str, ...] = (
    *_CREATION_VERBS,
    *_EXPLANATION_VERBS,
    "explanation of",
    "introduction to",
    "overview of",
    "tell me about",
)

#: Possessive determiners that bind a document noun to a specific existing
#: document ("my paper") rather than a generic artifact.
_SOURCE_POSSESSIVES: tuple[str, ...] = (
    "my", "our", "your", "their", "its", "his", "her",
)

#: Definite determiners that mark a document noun as a specific existing
#: document ("the paper").
_SOURCE_DETERMINERS: tuple[str, ...] = ("the", "this", "that")

#: Information verbs that, following a document noun, mark it as the source of
#: the answer ("the paper says", "the report shows").
_SOURCE_INFO_VERBS: tuple[str, ...] = (
    "says", "say", "stated", "state", "shows", "show",
    "contained", "contains", "contain", "covered", "covers", "cover",
    "discussed", "discusses", "discuss", "used", "uses", "use",
    "presented", "presents", "present", "included", "includes", "include",
    "mentioned", "mentions", "mention", "described", "describes",
    "explained", "explains",
)

#: Genitive prepositions that turn a document noun into the source of a
#: created artifact ("a summary of my paper") rather than the artifact itself.
_SOURCE_PREPOSITIONS: tuple[str, ...] = (
    "of", "from", "based on", "about", "regarding",
)

_DOCNOUN_ALTERNATION = "|".join(_DOCUMENT_NOUNS)

#: A document noun the user already owns ("my research paper").
_SOURCE_POSSESSIVE_PATTERN = re.compile(
    r"\b(?:{})\s+(?:\w+\s+){{0,3}}(?:{})\b".format(
        "|".join(_SOURCE_POSSESSIVES), _DOCNOUN_ALTERNATION
    )
)

#: A document noun used as the genitive source of a produced artifact
#: ("a summary of my research paper").
_SOURCE_GENITIVE_PATTERN = re.compile(
    r"\b(?:{})\s+(?:\w+\s+){{0,3}}(?:{})\b".format(
        "|".join(_SOURCE_PREPOSITIONS), _DOCNOUN_ALTERNATION
    )
)

#: A document noun referenced definitely ("the monocular depth estimation
#: paper").
_SOURCE_DEFINITE_PATTERN = re.compile(
    r"\b(?:{})\s+(?:\w+\s+){{0,3}}(?:{})\b".format(
        "|".join(_SOURCE_DETERMINERS), _DOCNOUN_ALTERNATION
    )
)

#: A document noun followed by an information verb ("the paper says").
_SOURCE_INFO_PATTERN = re.compile(
    r"\b(?:{})\s+(?:{})\b".format(
        _DOCNOUN_ALTERNATION, "|".join(_SOURCE_INFO_VERBS)
    )
)

#: Words that appear in upload advice about files not yet in the collection.
_UPLOAD_TOPIC_WORDS: tuple[str, ...] = (
    "upload", "uploaded", "uploading",
    "file", "files", "document", "documents",
)

#: Advice / planning markers that frame an upload question as about future
#: files rather than the user's already-uploaded documents.
_METADATA_ADVICE: tuple[str, ...] = (
    "should", "would", "recommend", "suggest", "need", "best",
    "supposed to", "going to", "plan to", "want to", "worth",
    "to upload",
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


def _is_future_upload_request(text: str) -> bool:
    """Return whether the question asks for advice about future uploads.

    An upload question framed with an advice / planning marker ("should",
    "recommend", "need", "to upload") is about files that do not exist in the
    collection yet, so it is not a metadata request about already-uploaded
    documents. Generic rather than pattern-specific: any advice marker plus any
    file/upload topic word triggers it.

    Args:
        text: The lowercased question text.

    Returns:
        True if the question asks which files to upload, False otherwise.
    """
    if not any(word in text for word in _UPLOAD_TOPIC_WORDS):
        return False
    return any(marker in text for marker in _METADATA_ADVICE)


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

    def classify(self, question: str, owner_id: str = "") -> QueryCategory:
        """Return the routing category for the given question.

        Deterministic rules take precedence. Only when they do not match is the
        question embedded and scored against the user's own corpus; below the
        relevance thresholds the question remains GENERAL.

        This is a convenience wrapper around :meth:`classify_with_embedding`
        that discards the generated embedding. Use
        ``classify_with_embedding`` when the caller needs the embedding for
        downstream retrieval so that the embedding always belongs to the
        current question.

        Args:
            question: The user's chat question.
            owner_id: The user id whose corpus determines relevance. Empty for
                the legacy ownerless path.

        Returns:
            The routing category for the question.
        """
        return self.classify_with_embedding(question, owner_id=owner_id).category

    def classify_with_embedding(
        self, question: str, owner_id: str = ""
    ) -> RouteResult:
        """Classify a query and return its request-local embedding.

        The embedding returned for a DOCUMENT query is generated from the
        *current* question and is never taken from shared instance state. This
        prevents a later query from reusing a previous query's embedding during
        semantic retrieval. The embedding is ``None`` for METADATA and GENERAL
        queries, which require no semantic retrieval (so no embedding is
        generated, preserving the no-wasted-call behavior).

        Args:
            question: The user's chat question.
            owner_id: The user id whose corpus determines relevance. Empty for
                the legacy ownerless path.

        Returns:
            A :class:`RouteResult` with the routing category and, when
            retrieval is required, the current question's embedding.
        """
        text = question.strip().lower()
        if self._is_metadata_intent(text):
            return RouteResult(QueryCategory.METADATA, None)
        if _DOCUMENT_EXTENSION_PATTERN.search(text):
            # Explicit filename reference: routed to DOCUMENT and needs
            # retrieval, so embed the current question here rather than relying
            # on any previously stored embedding.
            return RouteResult(QueryCategory.DOCUMENT, self._embed(question))
        if _is_future_upload_request(text):
            return RouteResult(QueryCategory.GENERAL, None)
        if self._is_general_ask(text):
            return RouteResult(QueryCategory.GENERAL, None)
        if self._embedding_service is None or self._relevance_scorer is None:
            return RouteResult(QueryCategory.GENERAL, None)
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
        if _is_future_upload_request(text):
            return False
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

    def _embed(self, question: str) -> list[float] | None:
        """Embed a single question, or return ``None`` if no service is set.

        Args:
            question: The question text to embed.

        Returns:
            The question embedding, or ``None`` when no embedding service is
            configured.
        """
        if self._embedding_service is None:
            return None
        return self._embedding_service.generate_embeddings([question])[0]

    def _classify_relevance(self, question: str, owner_id: str, text: str) -> RouteResult:
        """Embed once, combine signals, and route by the audited rule.

        The embedding is generated exactly once for the current question and
        returned (for DOCUMENT) so retrieval always uses the current question's
        vector rather than any shared cached state.
        """
        query_embedding = self._embed(question)
        if query_embedding is None:
            return RouteResult(QueryCategory.GENERAL, None)
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
                return RouteResult(QueryCategory.DOCUMENT, query_embedding)
        elif personal:
            if similarity >= self._personal_floor and lexical > 0.0:
                return RouteResult(QueryCategory.DOCUMENT, query_embedding)
        if docnoun and lexical > 0.0 and similarity >= self._docnoun_floor:
            return RouteResult(QueryCategory.DOCUMENT, query_embedding)
        if similarity >= self._topic_threshold:
            return RouteResult(QueryCategory.DOCUMENT, query_embedding)
        return RouteResult(QueryCategory.GENERAL, None)

    def _is_general_ask(self, text: str) -> bool:
        """Return whether the question is a general-knowledge generation ask.

        A creation / explanation frame ("write", "create", "explain", "what
        is") asks the LLM to produce general content about a topic. Such asks
        stay GENERAL even when the user's corpus is topically related, unless
        they anchor to an existing document:

        - personal reference ("my CV") or an explicit filename;
        - a creation verb whose document noun is the *source* of the produced
          artifact ("a summary of my paper", "write about the report");
        - an explanation ask that names a definite document ("explain the
          monocular depth estimation paper") or one followed by an information
          verb ("what the paper says").

        Args:
            text: The lowercased question text.

        Returns:
            True when the question is a general-knowledge generation ask.
        """
        if not any(frame in text for frame in _GENERAL_ASK_VERBS):
            return False
        if self._has_personal_reference(text):
            return False
        if _DOCUMENT_EXTENSION_PATTERN.search(text):
            return False
        if any(verb in text for verb in _CREATION_VERBS):
            if self._has_owned_document(text):
                return False
        elif self._has_definite_document(text):
            return False
        return True

    @staticmethod
    def _has_owned_document(text: str) -> bool:
        """Return whether a document noun is bound to an existing document.

        Possessive ("my paper") and genitive ("a summary of my paper")
        constructions reference a document the user already has, so the
        document noun is the source of a produced artifact, not the artifact
        being created.
        """
        if _SOURCE_POSSESSIVE_PATTERN.search(text):
            return True
        return _SOURCE_GENITIVE_PATTERN.search(text) is not None

    @staticmethod
    def _has_definite_document(text: str) -> bool:
        """Return whether an explanation ask names a specific existing document.

        A document noun referenced definitely ("the paper") or as the subject
        of an information verb ("the paper says") is the source of the answer,
        so the question is document-grounded rather than general knowledge.
        """
        return (
            _SOURCE_POSSESSIVE_PATTERN.search(text) is not None
            or _SOURCE_DEFINITE_PATTERN.search(text) is not None
            or _SOURCE_INFO_PATTERN.search(text) is not None
        )

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
        """Return whether the question asks about a personal self-attribute.

        Exact substring matches first; then single-edit-distance fuzzy matches
        on multi-word-free attributes so corrupted spellings such as
        "universty" still resolve to "university".
        """
        for attribute in _SELF_ATTRIBUTES:
            if attribute in text:
                return True
        tokens = _tokenize(text)
        for token in tokens:
            for attribute in _SELF_ATTRIBUTES:
                if " " in attribute or len(attribute) < 5:
                    continue
                if abs(len(token) - len(attribute)) > _MAX_EDIT_DISTANCE + 1:
                    continue
                if _edit_distance(token, attribute) <= _MAX_EDIT_DISTANCE:
                    return True
        return False
