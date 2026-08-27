"""Contract/integration tests for the Postgres metadata backend.

These prove the Postgres implementation satisfies the ``MetadataBackend``
interface and builds correct, ownership-aware queries without a live Postgres
server. The database session is mocked; queries are inspected by compiling them
against a Postgres dialect, and writes are captured as ORM objects.

Covered:
1. The Postgres implementation satisfies MetadataBackend.
2. add_documents maps chunks to rows with the correct fields.
3. get_document returns the positional record (with JSON-compatible id).
4. get_all_documents returns records in chunk_index order.
5. Owner / workspace filters are pushed into the SQL WHERE clause.
6. snapshot_documents / restore_documents roll back to the captured set.
7. Empty results return [].
8. No dependency on JSON files, JsonFileStore, or FAISS.
"""

from collections import namedtuple
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine

from app.db.models.chunk_metadata import ChunkMetadata
from app.services.storage_backends import MetadataBackend
from app.services.vectorstore.postgres_metadata_store import PostgresMetadataStore


ENGINE = create_engine("postgresql+psycopg://user:pass@localhost:5432/docmind")


class _FakeSession:
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
        # Support .scalars().all() used by get_all_documents.
        scalars = MagicMock()
        scalars.all.return_value = self._rows
        result.scalars.return_value = scalars
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

    return PostgresMetadataStore(session_factory=factory), fake


def _compiled_sql(stmt):
    return str(stmt.compile(ENGINE))


def _select_sql(fake_session):
    for stmt in fake_session.executed:
        sql = _compiled_sql(stmt)
        if "chunk_metadata" in sql and sql.strip().startswith("SELECT"):
            return sql
    raise AssertionError("no chunk_metadata SELECT was executed")


# ---------------------------------------------------------------------------
# 1. Interface satisfaction
# ---------------------------------------------------------------------------
def test_postgres_metadata_store_implements_metadata_backend():
    store, _ = _make_store()
    assert isinstance(store, MetadataBackend)


def test_postgres_metadata_backend_has_no_forbidden_dependencies():
    import app.services.vectorstore.postgres_metadata_store as mod

    with open(mod.__file__ or "") as fh:
        body = fh.read()
    assert "faiss" not in body
    assert "metadata.json" not in body
    assert "JsonFileStore" not in body


# ---------------------------------------------------------------------------
# 2. Insert/create behavior + mapping
# ---------------------------------------------------------------------------
def test_add_documents_maps_records_with_positional_index():
    store, fake = _make_store()
    store.add_documents(
        ["chunk one", "chunk two"],
        filename="doc.txt",
        workspace_id="ws1",
        document_id="d1",
        owner_id="u1",
    )

    assert len(fake.added) == 2
    for offset, obj in enumerate(fake.added):
        assert isinstance(obj, ChunkMetadata)
        assert obj.chunk_index == offset
        assert obj.document_id == "d1"
        assert obj.chunk_id == offset + 1
        assert obj.filename == "doc.txt"
        assert obj.owner_id == "u1"
        assert obj.workspace_id == "ws1"
        assert obj.text == ["chunk one", "chunk two"][offset]


def test_add_documents_derives_json_compatible_id():
    store, fake = _make_store()
    store.add_documents(["a", "b", "c"], filename="f.txt", owner_id="u2")
    # id is exposed by get_document as chunk_index + 1.
    rec = store._to_record(fake.added[0])
    assert rec["id"] == 1
    rec2 = store._to_record(fake.added[2])
    assert rec2["id"] == 3


# ---------------------------------------------------------------------------
# 3/4. get_document / get_all_documents
# ---------------------------------------------------------------------------
def test_get_document_returns_positional_record():
    Row = namedtuple("Row", ChunkMetadata.__table__.columns.keys())
    row = Row(
        id=10,
        chunk_index=3,
        document_id="d9",
        chunk_id=4,
        filename="f.pdf",
        owner_id="u1",
        workspace_id="ws1",
        text="hello world",
    )
    store, _ = _make_store(single=row)
    rec = store.get_document(3)
    assert rec == {
        "id": 4,
        "workspace_id": "ws1",
        "filename": "f.pdf",
        "chunk_id": 4,
        "document_id": "d9",
        "owner_id": "u1",
        "text": "hello world",
    }


def test_get_all_documents_returns_ordered_records():
    Row = namedtuple("Row", ChunkMetadata.__table__.columns.keys())
    rows = [
        Row(1, 0, "d", 1, "a.txt", "u1", "ws1", "first"),
        Row(2, 1, "d", 2, "a.txt", "u1", "ws1", "second"),
    ]
    store, _ = _make_store(rows=rows)
    docs = store.get_all_documents()
    assert [d["text"] for d in docs] == ["first", "second"]
    assert docs[0]["id"] == 1 and docs[1]["id"] == 2


# ---------------------------------------------------------------------------
# 5. Owner / workspace filtering pushed into SQL
# ---------------------------------------------------------------------------
def test_get_all_documents_without_filter_has_no_owner_where():
    store, fake = _make_store(rows=[])
    store.get_all_documents()
    sql = _select_sql(fake)
    # owner_id/workspace_id are returned columns; the distinction is the absence
    # of a WHERE clause (no DB-level filtering when no filter is requested).
    assert "WHERE" not in sql


def test_get_all_documents_with_owner_adds_owner_where():
    store, fake = _make_store(rows=[])
    store.get_all_documents(owner_id="u1")
    sql = _select_sql(fake)
    assert "WHERE" in sql
    assert "owner_id" in sql


def test_get_all_documents_with_workspace_adds_workspace_where():
    store, fake = _make_store(rows=[])
    store.get_all_documents(workspace_id="ws1")
    sql = _select_sql(fake)
    assert "WHERE" in sql
    assert "workspace_id" in sql


# ---------------------------------------------------------------------------
# 6. snapshot / restore rollback
# ---------------------------------------------------------------------------
def test_snapshot_documents_returns_copied_records():
    Row = namedtuple("Row", ChunkMetadata.__table__.columns.keys())
    rows = [
        Row(1, 0, "d1", 1, "a.txt", "u1", "ws1", "x"),
        Row(2, 1, "d1", 2, "a.txt", "u1", "ws1", "y"),
    ]
    store, _ = _make_store(rows=rows)
    snapshot = store.snapshot_documents()
    assert isinstance(snapshot, list)
    assert len(snapshot) == 2
    assert snapshot[0]["text"] == "x"
    assert snapshot[1]["owner_id"] == "u1"
    # Snapshot must be independent copies.
    snapshot[0]["text"] = "mutated"
    assert store.snapshot_documents()[0]["text"] == "x"


def test_restore_documents_replaces_all_records():
    store, fake = _make_store()
    records = [
        {
            "id": 1,
            "workspace_id": "ws1",
            "filename": "a.txt",
            "chunk_id": 1,
            "document_id": "d1",
            "owner_id": "u1",
            "text": "x",
        },
        {
            "id": 2,
            "workspace_id": "ws1",
            "filename": "a.txt",
            "chunk_id": 2,
            "document_id": "d1",
            "owner_id": "u1",
            "text": "y",
        },
    ]
    store.restore_documents(records)
    assert store.ntotal == 2
    assert len(fake.added) == 2
    # Records are re-inserted in positional order (chunk_index 0, 1).
    assert [obj.chunk_index for obj in fake.added] == [0, 1]

    delete_sql = [
        _compiled_sql(stmt)
        for stmt in fake.executed
        if _compiled_sql(stmt).strip().startswith("DELETE")
    ]
    assert delete_sql, "expected a DELETE statement for restore"
    assert any("chunk_metadata" in sql for sql in delete_sql)


# ---------------------------------------------------------------------------
# 7. Empty results
# ---------------------------------------------------------------------------
def test_get_all_documents_empty_returns_empty_list():
    store, _ = _make_store(rows=[])
    assert store.get_all_documents() == []


def test_get_document_out_of_range_raises():
    store, _ = _make_store(single=None)
    with pytest.raises(IndexError):
        store.get_document(42)
