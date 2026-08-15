import math
import re
from collections import Counter
from typing import Mapping

from app.repositories.interfaces import DocumentRepository
from app.services.retrieval.base import Retriever
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class BM25Retriever(Retriever):
    """Retrieve document chunks with Okapi BM25 keyword scoring.

    The BM25 index is built lazily from the chunk texts already stored in the
    shared MetadataStore, so document storage is not duplicated. Term
    statistics are global (document frequency, average length), while
    workspace/deletion filtering happens during retrieval.
    """

    K1 = 1.5
    B = 0.75

    def __init__(
        self,
        metadata_store: MetadataStore,
        document_registry: DocumentRepository | None = None,
    ) -> None:
        """Initialize the retriever, building the index on first use.

        Args:
            metadata_store: The shared store of document chunk metadata.
            document_registry: Optional registry used to exclude deleted docs.
        """
        self._metadata_store = metadata_store
        self._document_registry = document_registry
        self._doc_lengths: list[int] = []
        self._doc_tokens: list[Counter] = []
        self._avgdl: float = 0.0
        self._doc_freq: Counter = Counter()
        self._avgdl: float = 0.0
        self._built = False

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize text into lowercase alphanumeric terms.

        Args:
            text: The text to tokenize.

        Returns:
            A list of lowercase tokens.
        """
        return TOKEN_PATTERN.findall(text.lower())

    def _build(self) -> None:
        """Build the numerator/idf statistics from the metadata store."""
        documents = self._metadata_store.get_all_documents()
        self._doc_tokens = []
        self._doc_lengths = []
        self._doc_freq = Counter()
        for document in documents:
            tokens = self._tokenize(document.get("text", ""))
            term_counts = Counter(tokens)
            self._doc_tokens.append(term_counts)
            self._doc_lengths.append(sum(term_counts.values()))
            for term in term_counts:
                self._doc_freq[term] += 1
        total = sum(self._doc_lengths)
        self._avgdl = total / len(documents) if documents else 0.0
        self._built = True

    def _ensure_index(self) -> None:
        """Rebuild the BM25 index when the stored corpus has changed.

        The index is derived from the shared MetadataStore, which grows as new
        documents are uploaded. It was previously built only once, so chunks
        indexed after the first retrieval stayed invisible to BM25 until the
        backend restarted. Rebuild whenever the number of stored chunks no
        longer matches the number of indexed chunks so newly uploaded documents
        become searchable immediately, while keeping the build lazy and cheap on
        the common path where the corpus is unchanged.
        """
        document_count = len(self._metadata_store.get_all_documents())
        if not self._built or len(self._doc_tokens) != document_count:
            self._build()

    def retrieve(
        self,
        query: str,
        k: int = 5,
        workspace_id: str = DEFAULT_WORKSPACE,
        owner_id: str = "",
    ) -> list[dict]:
        """Retrieve the top-k chunks by BM25 relevance for the workspace.

        Args:
            query: The search query text.
            k: The number of chunks to return.
            workspace_id: Only chunks belonging to this workspace are returned.
            owner_id: Only chunks owned by this user are returned. Empty for
                legacy chunks indexed before ownership was tracked.

        Returns:
            A list of the top-k matching document chunks, ordered best first.
        """
        self._ensure_index()
        query_terms = set(self._tokenize(query))
        if not query_terms:
            return []

        scored: list[tuple[float, int]] = []
        for index, (term_counts, length) in enumerate(
            zip(self._doc_tokens, self._doc_lengths)
        ):
            document = self._metadata_store.get_document(index)
            if not self.is_eligible(document, workspace_id, owner_id):
                continue
            score = self._score(term_counts, length, query_terms)
            if score > 0.0:
                scored.append((score, index))
        scored.sort(key=lambda pair: pair[0], reverse=True)

        documents: list[dict] = []
        for _, index in scored[:k]:
            documents.append(self._metadata_store.get_document(index))
        return documents

    def _score(
        self,
        term_counts: Mapping[str, int],
        length: int,
        query_terms: set[str],
    ) -> float:
        """Compute the Okapi BM25 score for a document against query terms.

        Args:
            term_counts: The term frequencies of the document.
            length: The total token length of the document.
            query_terms: The set of query terms to score.

        Returns:
            The BM25 relevance score for the document.
        """
        num_documents = len(self._doc_tokens) or 1
        score = 0.0
        for term in query_terms:
            term_freq = term_counts.get(term, 0)
            if term_freq == 0:
                continue
            doc_freq = self._doc_freq[term]
            idf = math.log(
                (num_documents - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0
            )
            denominator = (
                term_freq
                + self.K1
                * (1.0 - self.B + self.B * length / self._avgdl)
            )
            score += idf * (term_freq * (self.K1 + 1.0)) / denominator
        return score

    def is_eligible(
        self,
        document: dict,
        workspace_id: str,
        owner_id: str = "",
    ) -> bool:
        """Return whether a chunk belongs to the workspace and owner.

        Args:
            document: The chunk metadata to check.
            workspace_id: The requested workspace.
            owner_id: The requested owner. Empty for legacy ownerless chunks.

        Returns:
            True if the chunk is in the workspace and owned by the user and its
            document is alive; False otherwise.
        """
        if document["workspace_id"] != workspace_id:
            return False
        if document.get("owner_id", "") != owner_id:
            return False
        document_id = document.get("document_id")
        if document_id and self._document_registry is not None:
            return not self._document_registry.is_deleted(document_id)
        return True