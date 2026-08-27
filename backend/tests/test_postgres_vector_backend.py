"""Contract/integration tests for the Postgres/pgvector VectorBackend.

These prove the Postgres implementation satisfies the ``VectorBackend``
interface and builds correct, ownership-aware queries without requiring a live
Postgres server. The database session is mocked: queries are inspected by
compiling them against a Postgres dialect, and writes are captured as ORM
objects.

Covered:
1. The Postgres implementation satisfies VectorBackend.
2. Embeddings map to VectorChunk rows with the correct positional chunk_index.
3. The search query uses pgvector distance ordering and a LIMIT.
4. Owner and workspace filters are pushed into the SQL WHERE clause.
5. Empty result sets return ([], []).
6. snapshot_state / restore_state roll back appended vectors (DELETE).
7. The implementation has no FAISS dependency.
"""

from collections import namedtuple
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine

from app.db.models.vector_chunk import VectorChunk
from app.services.storage_backends import VectorBackend, VectorSnapshot
from app.services.vectorstore.postgres_vector_store import PostgresVectorStore


ENGINE = create_engine("postgresql+psycopg://user:pass@localhost:5432/docmind")


class _FakeSession:
    """A minimal stand-in for a SQLAlchemy Session.

    Records added ORM objects and executed statements. Query results are
    driven by the ``rows`` / ``single`` the test configures.
    """

    def __init__(self, rows=None, single=None):
        self.added = []
        self.executed = []
        self._rows = rows or []
        self._single = single

    def add(self, obj):
        self.added.append(obj)

    def execute(self, stmt):
        self.executed.append(stmt)
        result = MagicMock()
        result.scalar.return_value = None
        result.all.return_value = self._rows
        result.first.return_value = self._single
        return result

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _make_store(rows=None, single=None):
    fake = _FakeSession(rows=rows, single=single)

    def factory():
        return fake

    store = PostgresVectorStore(dimension=4, session_factory=factory)
    return store, fake


def _compiled_sql(stmt):
    return str(stmt.compile(ENGINE))


def _search_sql(fake_session):
    # The search query is the executed statement containing the pgvector
    # distance operator (compiled as "<->", i.e. l2_distance).
    for stmt in fake_session.executed:
        sql = _compiled_sql(stmt)
        if "<->" in sql:
            return sql
    raise AssertionError("no vector search statement was executed")


# ---------------------------------------------------------------------------
# 1. Interface satisfaction
# ---------------------------------------------------------------------------
def test_postgres_vector_store_implements_vector_backend():
    store, _ = _make_store()
    assert isinstance(store, VectorBackend)


def test_postgres_backend_has_no_faiss_dependency():
    import app.services.vectorstore.postgres_vector_store as mod

    source_path = mod.__file__ or ""
    with open(source_path) as fh:
        body = fh.read()
    assert "faiss" not in body
    assert "index.faiss" not in body
    assert "metadata.json" not in body


# ---------------------------------------------------------------------------
# 2. Embedding mapping
# ---------------------------------------------------------------------------
def test_add_embeddings_maps_records_with_positional_index():
    store, fake = _make_store()
    store.add_embeddings(
        [
            [0.1, 0.0, 0.0, 0.0],
            [0.0, 0.2, 0.0, 0.0],
            [0.0, 0.0, 0.3, 0.0],
        ]
    )

    assert len(fake.added) == 3
    for offset, obj in enumerate(fake.added):
        assert isinstance(obj, VectorChunk)
        assert obj.chunk_index == offset
        assert obj.embedding == [
            [0.1, 0.0, 0.0, 0.0],
            [0.0, 0.2, 0.0, 0.0],
            [0.0, 0.0, 0.3, 0.0],
        ][offset]
        assert obj.owner_id == ""
        assert obj.workspace_id == ""
        assert obj.document_id == ""


# ---------------------------------------------------------------------------
# 3. Search query construction
# ---------------------------------------------------------------------------
def test_search_query_uses_distance_ordering_and_limit():
    Row = namedtuple("Row", ["chunk_index", "distance"])
    store, fake = _make_store(rows=[Row(0, 0.01), Row(2, 0.04)])
    distances, indices = store.search([0.1, 0.0, 0.0, 0.0], k=5)

    sql = _search_sql(fake)
    assert "<->" in sql
    assert "ORDER BY" in sql
    assert "LIMIT" in sql
    # Squared L2 matches FAISS IndexFlatL2 (multiply l2_distance by itself);
    # the "<->" operator appears twice in the projection and twice in ORDER BY.
    assert sql.count("<->") == 4

    assert indices == [[0, 2]]
    assert distances == [[0.01, 0.04]]


# ---------------------------------------------------------------------------
# 4. Ownership / workspace filtering pushed into SQL
# ---------------------------------------------------------------------------
def test_search_without_owner_has_no_owner_where():
    store, fake = _make_store(rows=[])
    store.search([0.1, 0.0, 0.0, 0.0], k=5)
    sql = _search_sql(fake)
    assert "owner_id" not in sql


def test_search_with_owner_adds_owner_where():
    store, fake = _make_store(rows=[])
    store.search([0.1, 0.0, 0.0, 0.0], k=5, owner_id="u1")
    sql = _search_sql(fake)
    assert "owner_id" in sql
    assert "WHERE" in sql


def test_search_with_workspace_adds_workspace_where():
    store, fake = _make_store(rows=[])
    store.search([0.1, 0.0, 0.0, 0.0], k=5, workspace_id="ws1")
    sql = _search_sql(fake)
    assert "workspace_id" in sql
    assert "WHERE" in sql


# ---------------------------------------------------------------------------
# 5. Empty results
# ---------------------------------------------------------------------------
def test_search_empty_results_return_empty_lists():
    store, _ = _make_store(rows=[])
    distances, indices = store.search([0.1, 0.0, 0.0, 0.0], k=5)
    assert distances == []
    assert indices == []


# ---------------------------------------------------------------------------
# 6. Snapshot / restore rollback
# ---------------------------------------------------------------------------
def test_snapshot_and_restore_deletes_appended_vectors():
    store, fake = _make_store()
    store.add_embeddings([[0.1, 0.0, 0.0, 0.0], [0.0, 0.2, 0.0, 0.0]])
    snapshot = store.snapshot_state()
    assert isinstance(snapshot, VectorSnapshot)
    assert snapshot.payload["watermark"] == 2

    store.add_embeddings([[0.0, 0.0, 0.3, 0.0]])
    assert store.ntotal == 3

    store.restore_state(snapshot)
    assert store.ntotal == 2

    # The restore issued a DELETE against vector_chunks at/after the watermark.
    delete_sql = [
        _compiled_sql(stmt)
        for stmt in fake.executed
        if _compiled_sql(stmt).strip().startswith("DELETE")
    ]
    assert delete_sql, "expected a DELETE statement for restore"
    assert any("vector_chunks" in sql and "chunk_index" in sql for sql in delete_sql)


# ---------------------------------------------------------------------------
# 7. get_embedding
# ---------------------------------------------------------------------------
def test_get_embedding_returns_stored_vector():
    store, _ = _make_store(single=([0.5, 0.0, 0.0, 0.0],))
    assert store.get_embedding(0) == [0.5, 0.0, 0.0, 0.0]


def test_get_embedding_out_of_range_raises():
    store, _ = _make_store(single=None)
    with pytest.raises(IndexError):
        store.get_embedding(99)
