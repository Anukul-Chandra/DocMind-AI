"""Regression tests for PromptBuilder natural conversation and language matching."""

import pytest

from app.services.llm.prompt_builder import PromptBuilder


@pytest.fixture
def builder():
    return PromptBuilder()


class TestLanguageMatching:
    """Prompts must instruct the model to mirror the user's language."""

    def test_rag_prompt_contains_language_instruction(self, builder):
        prompt = builder.build_prompt("hello", [])
        assert "same language" in prompt.text.lower()

    def test_general_prompt_contains_language_instruction(self, builder):
        prompt = builder.build_general_prompt("hello")
        assert "same language" in prompt.text.lower()

    def test_rag_prompt_mentions_banglish(self, builder):
        prompt = builder.build_prompt("ki obosta", [])
        assert "banglish" in prompt.text.lower()

    def test_general_prompt_mentions_banglish(self, builder):
        prompt = builder.build_general_prompt("ki obosta")
        assert "banglish" in prompt.text.lower()

    def test_rag_prompt_mentions_bengali(self, builder):
        prompt = builder.build_prompt("hello", [])
        assert "bengali" in prompt.text.lower()

    def test_general_prompt_mentions_bengali(self, builder):
        prompt = builder.build_general_prompt("hello")
        assert "bengali" in prompt.text.lower()


class TestNaturalConversation:
    """Prompts must instruct natural conversational responses."""

    def test_rag_prompt_discourages_self_introduction(self, builder):
        prompt = builder.build_prompt("hey", [])
        assert "do not introduce yourself" in prompt.text.lower()

    def test_general_prompt_discourages_self_introduction(self, builder):
        prompt = builder.build_general_prompt("hey")
        assert "do not introduce yourself" in prompt.text.lower()

    def test_rag_prompt_mentions_casual_messages(self, builder):
        prompt = builder.build_prompt("hi", [])
        assert "casual" in prompt.text.lower()

    def test_general_prompt_mentions_casual_messages(self, builder):
        prompt = builder.build_general_prompt("hi")
        assert "casual" in prompt.text.lower()


class TestNoInternalDetails:
    """Prompts must instruct the model to hide provider internals."""

    def test_rag_prompt_hides_provider_info(self, builder):
        prompt = builder.build_prompt("hello", [])
        assert "do not mention" in prompt.text.lower()
        assert "provider" in prompt.text.lower()

    def test_general_prompt_hides_provider_info(self, builder):
        prompt = builder.build_general_prompt("hello")
        assert "do not mention" in prompt.text.lower()
        assert "provider" in prompt.text.lower()


class TestPromptStructure:
    """Basic structural checks for both prompt builders."""

    def test_rag_prompt_includes_context(self, builder):
        contexts = [{"text": "doc content", "filename": "f.txt", "chunk_id": 0}]
        prompt = builder.build_prompt("what is this?", contexts)
        assert "doc content" in prompt.text
        assert "Question:" in prompt.text
        assert "Answer:" in prompt.text

    def test_rag_prompt_includes_history(self, builder):
        history = [{"role": "user", "content": "previous question"}]
        prompt = builder.build_prompt("follow up", [], history=history)
        assert "previous question" in prompt.text

    def test_general_prompt_includes_question(self, builder):
        prompt = builder.build_general_prompt("what is AI?")
        assert "what is AI?" in prompt.text
        assert "Question:" in prompt.text
        assert "Answer:" in prompt.text

    def test_rag_prompt_sources_populated(self, builder):
        contexts = [
            {"text": "a", "filename": "f1.txt", "chunk_id": 0},
            {"text": "b", "filename": "f2.txt", "chunk_id": 1},
        ]
        prompt = builder.build_prompt("q", contexts)
        assert len(prompt.sources) == 2
        assert prompt.sources[0]["filename"] == "f1.txt"

    def test_general_prompt_sources_empty(self, builder):
        prompt = builder.build_general_prompt("q")
        assert prompt.sources == []
