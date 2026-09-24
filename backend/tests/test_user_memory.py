"""Regression tests for authenticated user-scoped persistent memory."""

import asyncio
from pathlib import Path

from app.models.llm import LLMResponse
from app.repositories.json.user_memory_repository import JsonUserMemoryRepository
from app.services.chat.chat_service import ChatService
from app.services.chat.memory import ConversationMemory
from app.services.chat.query_router import QueryCategory, RouteResult
from app.services.llm.prompt_builder import PromptBuilder
from app.services.retrieval.base import Retriever


class CaptureProviderManager:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **_kwargs) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(text="answer", provider="test", model="test-model")


class GeneralRouter:
    def classify_with_embedding(self, question: str, owner_id: str = "") -> RouteResult:
        return RouteResult(QueryCategory.GENERAL)


class EmptyRetriever(Retriever):
    def retrieve(self, query, k=5, workspace_id="default", owner_id="", query_embedding=None):
        return []

    def is_eligible(self, document, workspace_id, owner_id=""):
        return True


def make_service(conversations, memories, provider) -> ChatService:
    return ChatService(
        retriever=EmptyRetriever(),
        prompt_builder=PromptBuilder(),
        provider_manager=provider,
        query_router=GeneralRouter(),
        conversation_repository=conversations,
        user_memory_repository=memories,
    )


def test_memory_is_available_in_a_new_chat_and_is_not_conversation_history(tmp_path: Path):
    conversations = ConversationMemory()
    memories = JsonUserMemoryRepository(tmp_path / "user_memories.json")
    provider = CaptureProviderManager()
    service = make_service(conversations, memories, provider)
    chat_a = conversations.create_conversation("user-a")
    chat_b = conversations.create_conversation("user-a")

    asyncio.run(
        service.chat(
            "My name is Anukul Chandra.",
            owner_id="user-a",
            conversation_id=chat_a,
        )
    )
    asyncio.run(
        service.chat(
            "Do you know my name?",
            owner_id="user-a",
            conversation_id=chat_b,
        )
    )

    prompt = provider.prompts[-1]
    assert "- name: Anukul Chandra" in prompt
    assert "User: My name is Anukul Chandra." not in prompt
    assert [memory.value for memory in memories.list_memories("user-a")] == [
        "Anukul Chandra"
    ]


def test_memory_isolation_and_explicit_update(tmp_path: Path):
    conversations = ConversationMemory()
    memories = JsonUserMemoryRepository(tmp_path / "user_memories.json")
    provider = CaptureProviderManager()
    service = make_service(conversations, memories, provider)
    user_a_chat = conversations.create_conversation("user-a")
    user_b_chat = conversations.create_conversation("user-b")

    asyncio.run(
        service.chat(
            "My name is Anukul Chandra.",
            owner_id="user-a",
            conversation_id=user_a_chat,
        )
    )
    asyncio.run(
        service.chat(
            "My name is Anukul Kumar.",
            owner_id="user-a",
            conversation_id=user_a_chat,
        )
    )
    asyncio.run(
        service.chat(
            "What is my name?",
            owner_id="user-b",
            conversation_id=user_b_chat,
        )
    )

    assert "Anukul Chandra" not in provider.prompts[-1]
    assert "Anukul Kumar" not in provider.prompts[-1]
    assert memories.list_memories("user-b") == []
    assert [memory.value for memory in memories.list_memories("user-a")] == [
        "Anukul Kumar"
    ]


def test_ordinary_messages_are_not_saved_as_memory(tmp_path: Path):
    conversations = ConversationMemory()
    memories = JsonUserMemoryRepository(tmp_path / "user_memories.json")
    provider = CaptureProviderManager()
    service = make_service(conversations, memories, provider)
    conversation_id = conversations.create_conversation("user-a")

    asyncio.run(
        service.chat(
            "What is the weather today?",
            owner_id="user-a",
            conversation_id=conversation_id,
        )
    )

    assert memories.list_memories("user-a") == []


def test_explicit_i_am_name_statement_is_saved():
    from app.services.chat.user_memory import UserMemoryExtractor

    candidate = UserMemoryExtractor().extract("I am Anukul Chandra.")

    assert candidate is not None
    assert candidate.key == "name"
    assert candidate.value == "Anukul Chandra"


def test_user_memory_survives_a_fresh_repository(tmp_path: Path):
    path = tmp_path / "user_memories.json"
    first = JsonUserMemoryRepository(path)
    first.upsert_memory("user-a", "name", "Anukul Chandra")

    second = JsonUserMemoryRepository(path)

    assert second.list_memories("user-a")[0].value == "Anukul Chandra"
    assert second.list_memories("user-b") == []