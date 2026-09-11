"""Regression tests for conversation history passed into LLM prompts."""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

import pytest
from app.models.llm import LLMResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.memory import ConversationMemory
from app.services.chat.query_router import QueryCategory, RouteResult
from app.services.llm.prompt_builder import PromptBuilder
from app.services.retrieval.base import Retriever


class CaptureProviderManager:
    """Provider substitute that records the exact prompt sent by ChatService."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **_kwargs) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(text="answer", provider="test", model="test-model")


class GeneralRouter:
    def classify_with_embedding(self, question: str, owner_id: str = "") -> RouteResult:
        return RouteResult(QueryCategory.GENERAL)


class DocumentRouter:
    def classify_with_embedding(self, question: str, owner_id: str = "") -> RouteResult:
        return RouteResult(QueryCategory.DOCUMENT, [1.0])


class StaticRetriever(Retriever):
    def retrieve(self, query, k=5, workspace_id="default", owner_id="", query_embedding=None):
        return [{"text": "Relevant document fact.", "filename": "notes.txt", "chunk_id": 1}]

    def is_eligible(self, document, workspace_id, owner_id=""):
        return True


def make_service(repository, provider, router) -> ChatService:
    return ChatService(
        retriever=StaticRetriever(),
        prompt_builder=PromptBuilder(),
        provider_manager=provider,
        query_router=router,
        conversation_repository=repository,
    )


def test_same_conversation_history_reaches_general_llm_prompt():
    repository = ConversationMemory()
    provider = CaptureProviderManager()
    service = make_service(repository, provider, GeneralRouter())
    conversation_id = repository.create_conversation("user-a")

    asyncio.run(service.chat("My name is Anukul.", owner_id="user-a", conversation_id=conversation_id))
    asyncio.run(service.chat("What is my name?", owner_id="user-a", conversation_id=conversation_id))

    prompt = provider.prompts[-1]
    assert "User: My name is Anukul." in prompt
    assert prompt.index("User: My name is Anukul.") < prompt.index("What is my name?")


def test_history_is_isolated_to_the_current_conversation():
    repository = ConversationMemory()
    provider = CaptureProviderManager()
    service = make_service(repository, provider, GeneralRouter())
    conversation_a = repository.create_conversation("user-a")
    conversation_b = repository.create_conversation("user-a")

    asyncio.run(service.chat(
        "My secret test word is APPLE.", owner_id="user-a", conversation_id=conversation_a
    ))
    asyncio.run(service.chat(
        "What is my secret test word?", owner_id="user-a", conversation_id=conversation_b
    ))

    assert "APPLE" not in provider.prompts[-1]


def test_persisted_existing_conversation_history_is_loaded():
    repository = ConversationMemory()
    provider = CaptureProviderManager()
    service = make_service(repository, provider, GeneralRouter())
    conversation_id = repository.create_conversation("user-a")
    repository.add_exchange(conversation_id, "user-a", "Persisted fact: BLUE.", "Noted.")

    asyncio.run(service.chat("What was the fact?", owner_id="user-a", conversation_id=conversation_id))

    assert "User: Persisted fact: BLUE." in provider.prompts[-1]
    assert "Assistant: Noted." in provider.prompts[-1]


def test_rag_prompt_contains_history_and_document_context():
    repository = ConversationMemory()
    provider = CaptureProviderManager()
    service = make_service(repository, provider, DocumentRouter())
    conversation_id = repository.create_conversation("user-a")
    repository.add_exchange(conversation_id, "user-a", "Remember this detail.", "I will.")

    asyncio.run(service.chat("Use the document and our chat.", owner_id="user-a", conversation_id=conversation_id))

    prompt = provider.prompts[-1]
    assert "User: Remember this detail." in prompt
    assert "Relevant document fact." in prompt
    assert prompt.index("User: Remember this detail.") < prompt.index("Use the document and our chat.")


def test_new_conversation_has_no_prior_conversation_history():
    repository = ConversationMemory()
    provider = CaptureProviderManager()
    service = make_service(repository, provider, GeneralRouter())
    prior = repository.create_conversation("user-a")
    fresh = repository.create_conversation("user-a")
    repository.add_exchange(prior, "user-a", "Prior-only token: ORANGE.", "Okay.")

    asyncio.run(service.chat("What is new?", owner_id="user-a", conversation_id=fresh))

    assert "ORANGE" not in provider.prompts[-1]


def test_file_backed_history_reaches_llm_prompt(tmp_path: Path):
    storage = tmp_path / "conversations.json"
    repository = ConversationMemory(storage)
    provider = CaptureProviderManager()
    service = make_service(repository, provider, GeneralRouter())
    conversation_id = repository.create_conversation("user-a")

    asyncio.run(service.chat("I am Anukul.", owner_id="user-a", conversation_id=conversation_id))
    asyncio.run(service.chat("What is my name?", owner_id="user-a", conversation_id=conversation_id))

    prompt = provider.prompts[-1]
    assert "User: I am Anukul." in prompt
    assert prompt.index("User: I am Anukul.") < prompt.index("What is my name?")
    assert "Conversation history:" in prompt


def test_file_backed_history_survives_fresh_repository(tmp_path: Path):
    storage = tmp_path / "conversations.json"
    first = ConversationMemory(storage)
    conversation_id = first.create_conversation("user-a")
    first.add_exchange(conversation_id, "user-a", "I am Anukul.", "Got it.")

    second = ConversationMemory(storage)
    messages = second.get_messages(conversation_id, "user-a")
    assert len(messages) == 2
    assert messages[0].content == "I am Anukul."
    assert messages[1].content == "Got it."


def test_file_backed_history_loaded_into_chat_service(tmp_path: Path):
    storage = tmp_path / "conversations.json"
    first = ConversationMemory(storage)
    conversation_id = first.create_conversation("user-a")
    first.add_exchange(conversation_id, "user-a", "I am Anukul.", "Got it.")

    second = ConversationMemory(storage)
    provider = CaptureProviderManager()
    service = make_service(second, provider, GeneralRouter())

    asyncio.run(service.chat("What is my name?", owner_id="user-a", conversation_id=conversation_id))

    prompt = provider.prompts[-1]
    assert "User: I am Anukul." in prompt
    assert "Assistant: Got it." in prompt


def test_file_backed_full_conversation_flow(tmp_path: Path):
    storage = tmp_path / "conversations.json"
    repository = ConversationMemory(storage)
    conversation_id = repository.create_conversation("user-a")

    provider = CaptureProviderManager()
    service = make_service(repository, provider, GeneralRouter())

    asyncio.run(service.chat("I am Anukul.", owner_id="user-a", conversation_id=conversation_id))

    assert repository.get_messages(conversation_id, "user-a") is not None
    assert len(repository.get_messages(conversation_id, "user-a")) == 2

    fresh_repository = ConversationMemory(storage)
    fresh_provider = CaptureProviderManager()
    fresh_service = make_service(fresh_repository, fresh_provider, GeneralRouter())

    history = fresh_service._load_history(conversation_id, "user-a")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "I am Anukul."

    asyncio.run(fresh_service.chat("What is my name?", owner_id="user-a", conversation_id=conversation_id))

    prompt = fresh_provider.prompts[-1]
    assert "User: I am Anukul." in prompt
    assert "What is my name?" in prompt
    assert prompt.index("User: I am Anukul.") < prompt.index("What is my name?")


def test_persistence_failure_is_logged_not_silent(monkeypatch, tmp_path: Path, caplog):
    storage = tmp_path / "conversations.json"
    repository = ConversationMemory(storage)
    conversation_id = repository.create_conversation("user-a")

    def failing_save(path, data):
        raise IOError("disk full")

    monkeypatch.setattr("app.services.storage.json_file_store.JsonFileStore.save", failing_save)

    provider = CaptureProviderManager()
    service = make_service(repository, provider, GeneralRouter())

    with caplog.at_level(logging.WARNING, logger="app.services.chat.chat_service"):
        asyncio.run(service.chat("Test message", owner_id="user-a", conversation_id=conversation_id))

    assert any(
        "Failed to record exchange" in record.message
        for record in caplog.records
    )
    assert provider.prompts


def test_record_exchange_logs_persistence_errors(monkeypatch, tmp_path: Path, caplog):
    storage = tmp_path / "conversations.json"
    repository = ConversationMemory(storage)

    def failing_add_exchange(*args, **kwargs):
        raise IOError("disk full")

    monkeypatch.setattr(repository, "add_exchange", failing_add_exchange)

    provider = CaptureProviderManager()
    service = make_service(repository, provider, GeneralRouter())
    conversation_id = repository.create_conversation("user-a")

    with caplog.at_level(logging.WARNING, logger="app.services.chat.chat_service"):
        asyncio.run(service.chat("Test message", owner_id="user-a", conversation_id=conversation_id))

    assert any(
        "Failed to record exchange" in record.message
        for record in caplog.records
    )
    assert provider.prompts
