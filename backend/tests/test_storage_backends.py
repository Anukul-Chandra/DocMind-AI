"""Contract tests for the vector/metadata storage backend abstractions.

These verify that:

1. The production FAISS ``VectorStore`` and JSON ``MetadataStore`` satisfy the
   provider-independent ``VectorBackend`` / ``MetadataBackend`` interfaces.
2. The upper layers (``SemanticRetriever``, ``BM25Retriever``) depend only on
   the abstraction, not on FAISS/JSON specifics (proven with an in-memory fake
   backend that implements the interface without any FAISS or filesystem use).
3. Persistence, snapshot/restore rollback, and ownership filtering behave
   exactly as before (behavior-preserving refactor).
4. No pgvector / Postgres dependency is introduced by the abstraction.
"""

import sys

import pytest

from app.services.storage_backends import (
    MetadataBackend,
    VectorBackend,
    VectorSnapshot,
)
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import SemanticRetriever
from app.services.retrieval.bm25_retriever import BM25Retriever


DIM = 4


# ---------------------------------------------------------------------------
# Abstraction satisfaction
# ---------------------------------------------------------------------------
def test_faiss_vector_store_implements_vector_backend():
    assert isinstance(VectorStore(DIM), VectorBackend)


def test_json_metadata_store_implements_metadata_backend():
    assert isinstance(MetadataStore(), MetadataBackend)


def test_storage_backends_module_has_no_pgvector_dependency():
    import app.services.storage_backends as mod

    # The abstraction must not pull in a database driver or storage backend.
    assert "pgvector" not in sys.modules
    source = (mod.__file__ or "")
    with open(source) as fh:
        body = fh.read()
    assert "pgvector" not in body
    assert "sqlalchemy" not in body
    assert "postgres" not in body


# ---------------------------------------------------------------------------
# FAISS VectorStore behavior through the abstraction
# ---------------------------------------------------------------------------
def test_vector_backend_persist_and_reload(tmp_path):
    index_path = str(tmp_path / "index.faiss")
    store = VectorStore(DIM, index_path=index_path)
    store.add_embeddings(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ]
    )
    store.persist()

    reloaded = VectorStore.load(index_path, DIM)
    assert reloaded.ntotal == 2
    _, indices = reloaded.search([1.0, 0.0, 0.0, 0.0], k=1)
    assert indices[0][0] == 0
    assert reloaded.get_embedding(1) == [0.0, 1.0, 0.0, 0.0]


def test_vector_backend_snapshot_restore_rollback():
    store = VectorStore(DIM)
    store.add_embeddings([[1.0, 0.0, 0.0, 0.0]])
    snapshot = store.snapshot_state()
    assert isinstance(snapshot, VectorSnapshot)

    store.add_embeddings([[0.0, 1.0, 0.0, 0.0]])
    assert store.ntotal == 2

    store.restore_state(snapshot)
    assert store.ntotal == 1


def test_vector_backend_persist_is_noop_without_path():
    store = VectorStore(DIM)
    store.add_embeddings([[1.0, 0.0, 0.0, 0.0]])
    # Must not raise even though no persistence path is configured.
    store.persist()
    assert store.ntotal == 1


# ---------------------------------------------------------------------------
# JSON MetadataStore behavior through the abstraction
# ---------------------------------------------------------------------------
def test_metadata_backend_persist_and_reload(tmp_path):
    path = str(tmp_path / "metadata.json")
    store = MetadataStore(path=path)
    store.add_documents(
        ["hello world", "goodbye moon"],
        filename="doc.txt",
        workspace_id="ws1",
        document_id="d1",
        owner_id="u1",
    )
    store.persist()

    reloaded = MetadataStore(path=path)
    assert len(reloaded.get_all_documents()) == 2
    record = reloaded.get_document(0)
    assert record["text"] == "hello world"
    assert record["owner_id"] == "u1"
    assert record["workspace_id"] == "ws1"


def test_metadata_backend_snapshot_restore_rollback():
    store = MetadataStore()
    store.add_documents(["a"], filename="a.txt", owner_id="u1")
    snap = store.snapshot_documents()
    store.add_documents(["b"], filename="b.txt", owner_id="u2")
    assert len(store.get_all_documents()) == 2

    store.restore_documents(snap)
    assert len(store.get_all_documents()) == 1
    assert store.get_all_documents()[0]["text"] == "a"


# ---------------------------------------------------------------------------
# Upper layers depend only on the abstraction (proven with a fake backend)
# ---------------------------------------------------------------------------
class _FakeVectorBackend(VectorBackend):
    def __init__(self):
        self.vectors = []
        self.records = []  # parallel metadata kept by a paired fake

    def add_embeddings(self, embeddings):
        self.vectors.extend(embeddings)

    def search(self, query_embedding, k=5):
        # Brute-force L2 over stored vectors.
        import numpy as np

        q = np.asarray(query_embedding, dtype=np.float32)
        dists = []
        for v in self.vectors:
            dists.append(float(np.linalg.norm(q - np.asarray(v, dtype=np.float32))))
        order = sorted(range(len(dists)), key=lambda i: dists[i])
        top = order[:k]
        return ([dists[i] for i in top], [top])

    def get_embedding(self, index):
        return list(self.vectors[index])

    def snapshot_state(self):
        return VectorSnapshot(list(self.vectors))

    def restore_state(self, state):
        self.vectors = list(state.payload)

    def persist(self):
        return None


class _StubEmbeddingService:
    def generate_embeddings(self, texts):
        return [[float(len(t) % 3), 0.0, 0.0, 0.0] for t in texts]


def test_semantic_retriever_works_through_abstraction():
    vector = _FakeVectorBackend()
    meta = MetadataStore()
    meta.add_documents(
        ["owned by alice", "owned by bob"],
        filename="doc.txt",
        workspace_id="default",
        document_id="d1",
        owner_id="alice",
    )
    # Second chunk belongs to a different owner.
    meta.add_documents(
        ["owned by bob"],
        filename="doc2.txt",
        workspace_id="default",
        document_id="d2",
        owner_id="bob",
    )
    vector.add_embeddings([[1.0, 0.0, 0.0, 0.0], [2.0, 0.0, 0.0, 0.0], [3.0, 0.0, 0.0, 0.0]])

    retriever = SemanticRetriever(_StubEmbeddingService(), vector, meta)

    alice_results = retriever.retrieve("query", k=10, owner_id="alice")
    assert {r["owner_id"] for r in alice_results} == {"alice"}
    assert len(alice_results) == 2

    bob_results = retriever.retrieve("query", k=10, owner_id="bob")
    assert {r["owner_id"] for r in bob_results} == {"bob"}
    assert len(bob_results) == 1


def test_bm25_retriever_works_through_abstraction():
    meta = MetadataStore()
    meta.add_documents(
        ["machine learning model training"],
        filename="ml.txt",
        workspace_id="default",
        document_id="d1",
        owner_id="alice",
    )
    meta.add_documents(
        ["dessert recipe with chocolate"],
        filename="food.txt",
        workspace_id="default",
        document_id="d2",
        owner_id="bob",
    )

    retriever = BM25Retriever(meta)
    alice_hits = retriever.retrieve("machine learning", k=5, owner_id="alice")
    assert len(alice_hits) == 1
    assert alice_hits[0]["owner_id"] == "alice"

    bob_hits = retriever.retrieve("chocolate dessert", k=5, owner_id="bob")
    assert len(bob_hits) == 1
    assert bob_hits[0]["owner_id"] == "bob"
