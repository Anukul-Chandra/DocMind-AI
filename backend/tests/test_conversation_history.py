"""Tests for per-user conversation history persistence and ownership.

Covers both the JSON file-backed memory and the PostgreSQL repository against
the shared ``ConversationRepository`` behavior, the ownership-scoped
``ConversationsService``, and the generator of deterministic conversation
titles. The Postgres implementation is exercised against an in-memory SQLite
database bound to the same ORM models, so no live Postgres server is required.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import models as db
from app.db.base import Base
from app.repositories.interfaces import ConversationRepository
from app.repositories.json.conversation_repository import JsonConversationRepository
from app.repositories.postgres.conversation_repository import (
    PostgresConversationRepository,
)
from app.services.chat.conversations_service import (
    ConversationNotFoundError,
    ConversationsService,
)
from app.services.chat.memory import ConversationMemory


def _json_repo(tmp_path: Path) -> JsonConversationRepository:
    """Return a JsonConversationRepository backed by a temp JSON file.

    Args:
        tmp_path: The pytest temporary directory.

    Returns:
        A file-backed JSON conversation repository.
    """
    return JsonConversationRepository(
        ConversationMemory(tmp_path / "conversations.json")
    )


@pytest.fixture
def postgres_repo() -> PostgresConversationRepository:
    """Return a PostgresConversationRepository bound to in-memory SQLite.

    The ORM models are created in a fresh in-memory SQLite database so the
    repository executes real SQL without needing Postgres.

    Returns:
        A PostgreSQL conversation repository backed by SQLite.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return PostgresConversationRepository(factory)


@pytest.fixture(params=["json", "postgres"])
def repo(request, tmp_path, postgres_repo) -> ConversationRepository:
    """Parameterize tests across both repository backends.

    Args:
        request: The pytest fixture request (parameter value selects backend).
        tmp_path: The pytest temporary directory.
        postgres_repo: The Postgres-backed repository fixture.

    Returns:
        A conversation repository of the selected backend.
    """
    if request.param == "postgres":
        return postgres_repo
    return _json_repo(tmp_path)


ALICE = "user-alice"
BOB = "user-bob"


class TestCreateList:
    def test_create_and_list_empty(self, repo: ConversationRepository) -> None:
        conversation_id = repo.create_conversation(ALICE)
        metas = repo.list_conversations(ALICE)
        assert [meta.conversation_id for meta in metas] == [conversation_id]
        assert metas[0].owner_id == ALICE
        assert metas[0].title is None
        assert metas[0].message_count == 0

    def test_list_is_empty_for_other_users(self, repo: ConversationRepository) -> None:
        repo.create_conversation(ALICE)
        assert repo.list_conversations(BOB) == []


class TestMessagesAndTitle:
    def test_add_exchange_records_user_then_assistant(
        self, repo: ConversationRepository
    ) -> None:
        conversation_id = repo.create_conversation(ALICE)
        repo.add_exchange(
            conversation_id, ALICE, "Hello there", "Hi! How can I help?"
        )
        messages = repo.get_messages(conversation_id, ALICE)
        assert [message.role for message in messages] == ["user", "assistant"]
        assert messages[0].content == "Hello there"
        assert messages[1].content == "Hi! How can I help?"

    def test_title_derived_from_first_user_message(
        self, repo: ConversationRepository
    ) -> None:
        conversation_id = repo.create_conversation(ALICE)
        repo.add_exchange(conversation_id, ALICE, "Summarize my AI paper", "Sure.")
        meta = repo.get_conversation(conversation_id, ALICE)
        assert meta is not None
        assert meta.title == "Summarize my AI paper"
        assert meta.message_count == 2

    def test_title_not_overwritten_on_later_exchanges(
        self, repo: ConversationRepository
    ) -> None:
        conversation_id = repo.create_conversation(ALICE)
        repo.add_exchange(conversation_id, ALICE, "First question", "First answer")
        repo.add_exchange(conversation_id, ALICE, "Second question", "Second answer")
        meta = repo.get_conversation(conversation_id, ALICE)
        assert meta is not None
        assert meta.title == "First question"

    def test_title_uses_default_for_blank_message(
        self, repo: ConversationRepository
    ) -> None:
        conversation_id = repo.create_conversation(ALICE)
        repo.add_exchange(conversation_id, ALICE, "   ", "answer")
        meta = repo.get_conversation(conversation_id, ALICE)
        assert meta is not None
        assert meta.title == "New chat"

    def test_title_truncated_with_ellipsis(self, repo: ConversationRepository) -> None:
        conversation_id = repo.create_conversation(ALICE)
        long_question = "word " * 100
        repo.add_exchange(conversation_id, ALICE, long_question, "answer")
        meta = repo.get_conversation(conversation_id, ALICE)
        assert meta is not None
        assert meta.title is not None
        assert meta.title.endswith("…")
        assert len(meta.title) <= 61


class TestOwnershipIsolation:
    def test_get_conversation_scoped_to_owner(
        self, repo: ConversationRepository
    ) -> None:
        conversation_id = repo.create_conversation(ALICE)
        assert repo.get_conversation(conversation_id, ALICE) is not None
        assert repo.get_conversation(conversation_id, BOB) is None

    def test_get_messages_scoped_to_owner(
        self, repo: ConversationRepository
    ) -> None:
        conversation_id = repo.create_conversation(ALICE)
        repo.add_exchange(conversation_id, ALICE, "q", "a")
        assert repo.get_messages(conversation_id, BOB) == []

    def test_add_exchange_ignored_for_cross_owner(
        self, repo: ConversationRepository
    ) -> None:
        conversation_id = repo.create_conversation(ALICE)
        repo.add_exchange(conversation_id, BOB, "hijack", "no")
        assert repo.get_messages(conversation_id, ALICE) == []
        assert repo.get_conversation(conversation_id, ALICE).title is None

    def test_rename_scoped_to_owner(self, repo: ConversationRepository) -> None:
        conversation_id = repo.create_conversation(ALICE)
        assert not repo.rename_conversation(conversation_id, BOB, "mine")
        assert repo.rename_conversation(conversation_id, ALICE, "mine")
        assert repo.get_conversation(conversation_id, ALICE).title == "mine"

    def test_delete_scoped_to_owner(self, repo: ConversationRepository) -> None:
        conversation_id = repo.create_conversation(ALICE)
        assert not repo.delete_conversation(conversation_id, BOB)
        assert repo.delete_conversation(conversation_id, ALICE)
        assert repo.list_conversations(ALICE) == []

    def test_delete_removes_messages(self, postgres_repo) -> None:
        conversation_id = postgres_repo.create_conversation(ALICE)
        postgres_repo.add_exchange(conversation_id, ALICE, "q", "a")
        assert postgres_repo.delete_conversation(conversation_id, ALICE)
        assert postgres_repo.get_messages(conversation_id, ALICE) == []


class TestMetadata:
    def test_owner_filtered_list_across_users(self, repo: ConversationRepository) -> None:
        a1 = repo.create_conversation(ALICE)
        b1 = repo.create_conversation(BOB)
        a2 = repo.create_conversation(ALICE)
        repo.add_exchange(a1, ALICE, "first alice", "x")
        repo.add_exchange(b1, BOB, "bob chat", "x")
        repo.add_exchange(a2, ALICE, "second alice", "x")

        alice_ids = [meta.conversation_id for meta in repo.list_conversations(ALICE)]
        bob_ids = [meta.conversation_id for meta in repo.list_conversations(BOB)]
        assert set(alice_ids) == {a1, a2}
        assert set(bob_ids) == {b1}

    def test_list_returns_all_owned(self, repo: ConversationRepository) -> None:
        c1 = repo.create_conversation(ALICE)
        c2 = repo.create_conversation(ALICE)
        repo.add_exchange(c1, ALICE, "older", "a")
        ids = [meta.conversation_id for meta in repo.list_conversations(ALICE)]
        assert set(ids) == {c1, c2}


class TestJsonPersistenceAcrossInstances:
    def test_history_survives_new_memory_instance(self, tmp_path: Path) -> None:
        path = tmp_path / "conversations.json"
        first = JsonConversationRepository(ConversationMemory(path))
        conversation_id = first.create_conversation(ALICE)
        first.add_exchange(conversation_id, ALICE, "persisted question", "answer")

        second = JsonConversationRepository(ConversationMemory(path))
        messages = second.get_messages(conversation_id, ALICE)
        assert [message.content for message in messages] == [
            "persisted question",
            "answer",
        ]
        assert second.get_conversation(conversation_id, ALICE).title == "persisted question"


class TestConversationsService:
    def test_create_get_rename_delete(self, repo: ConversationRepository) -> None:
        service = ConversationsService(repo)

        meta = service.create(ALICE)
        assert service.get(meta.conversation_id, ALICE).conversation_id == meta.conversation_id

        renamed = service.rename(meta.conversation_id, ALICE, "New title")
        assert renamed.title == "New title"

        service.delete(meta.conversation_id, ALICE)
        with pytest.raises(ConversationNotFoundError):
            service.get(meta.conversation_id, ALICE)

    def test_get_denied_for_other_owner(self, repo: ConversationRepository) -> None:
        service = ConversationsService(repo)
        meta = service.create(ALICE)
        with pytest.raises(ConversationNotFoundError):
            service.get(meta.conversation_id, BOB)
        with pytest.raises(ConversationNotFoundError):
            service.get_messages(meta.conversation_id, BOB)
        with pytest.raises(ConversationNotFoundError):
            service.rename(meta.conversation_id, BOB, "hijack")
        with pytest.raises(ConversationNotFoundError):
            service.delete(meta.conversation_id, BOB)

    def test_get_messages_after_exchange(self, repo: ConversationRepository) -> None:
        service = ConversationsService(repo)
        meta = service.create(ALICE)
        repo.add_exchange(meta.conversation_id, ALICE, "q", "a")
        messages = service.get_messages(meta.conversation_id, ALICE)
        assert len(messages) == 2
