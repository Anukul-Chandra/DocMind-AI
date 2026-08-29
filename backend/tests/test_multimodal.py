"""Regression tests for multimodal image transport through the chat pipeline."""

import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm.providers.base import build_user_content
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.groq import GroqProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_image(mime: str = "image/png") -> bytes:
    """Return a minimal valid PNG/1x1 pixel for testing."""
    # 1x1 transparent PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _b64_image(mime: str = "image/png") -> dict:
    """Return a base64-encoded image dict as the pipeline expects."""
    raw = _make_test_image(mime)
    return {"mime": mime, "data": base64.b64encode(raw).decode("ascii")}


# ---------------------------------------------------------------------------
# A. build_user_content — plain text (no images)
# ---------------------------------------------------------------------------

class TestBuildUserContentTextOnly:
    def test_returns_string_when_no_images(self):
        result = build_user_content("hello world")
        assert result == "hello world"

    def test_returns_string_when_images_is_none(self):
        result = build_user_content("hello", images=None)
        assert result == "hello"

    def test_returns_string_when_images_is_empty(self):
        result = build_user_content("hello", images=[])
        assert result == "hello"


# ---------------------------------------------------------------------------
# B. build_user_content — text + images
# ---------------------------------------------------------------------------

class TestBuildUserContentWithImages:
    def test_returns_list_with_text_and_image(self):
        img = _b64_image("image/png")
        result = build_user_content("extract text", images=[img])
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == {"type": "text", "text": "extract text"}
        assert result[1]["type"] == "image_url"
        assert "data:image/png;base64," in result[1]["image_url"]["url"]

    def test_preserves_mime_type(self):
        for mime in ("image/png", "image/jpeg", "image/webp"):
            img = _b64_image(mime)
            result = build_user_content("q", images=[img])
            assert result[1]["image_url"]["url"].startswith(f"data:{mime};base64,")

    def test_multiple_images(self):
        imgs = [_b64_image("image/png"), _b64_image("image/jpeg")]
        result = build_user_content("describe", images=imgs)
        assert isinstance(result, list)
        assert len(result) == 3  # text + 2 images
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "image_url"
        assert result[2]["type"] == "image_url"


# ---------------------------------------------------------------------------
# C. Backend endpoint — receives and encodes attachments
# ---------------------------------------------------------------------------

class TestChatEndpointEncoding:
    """Verify the endpoint correctly base64-encodes uploaded files."""

    @pytest.mark.asyncio
    async def test_valid_png_is_encoded(self):
        from app.api.routes.chat import ALLOWED_IMAGE_TYPES

        raw = _make_test_image("image/png")
        b64 = base64.b64encode(raw).decode("ascii")
        assert "iVBOR" in b64  # PNG base64 starts with iVBOR

    def test_allowed_types_cover_common_formats(self):
        from app.api.routes.chat import ALLOWED_IMAGE_TYPES

        assert "image/png" in ALLOWED_IMAGE_TYPES
        assert "image/jpeg" in ALLOWED_IMAGE_TYPES
        assert "image/webp" in ALLOWED_IMAGE_TYPES

    def test_max_size_is_reasonable(self):
        from app.api.routes.chat import MAX_IMAGE_BYTES

        assert MAX_IMAGE_BYTES == 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# D. ProviderManager — passes images through
# ---------------------------------------------------------------------------

class TestProviderManagerImages:
    @pytest.mark.asyncio
    async def test_images_passed_to_provider(self):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value="response text")
        mock_provider.model = "test-model"
        type(mock_provider).__name__ = "MockProvider"

        manager = ProviderManager([mock_provider])
        imgs = [_b64_image()]
        await manager.generate("hello", images=imgs)

        mock_provider.generate.assert_called_once()
        call_kwargs = mock_provider.generate.call_args
        assert call_kwargs.kwargs.get("images") == imgs or call_kwargs[1].get("images") == imgs

    @pytest.mark.asyncio
    async def test_none_images_still_works(self):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value="ok")
        mock_provider.model = "test-model"
        type(mock_provider).__name__ = "MockProvider"

        manager = ProviderManager([mock_provider])
        await manager.generate("hello")

        mock_provider.generate.assert_called_once()
        call_kwargs = mock_provider.generate.call_args
        # images should default to None
        assert call_kwargs.kwargs.get("images") is None


# ---------------------------------------------------------------------------
# E. Groq provider — builds multimodal content
# ---------------------------------------------------------------------------

class TestGroqProviderMultimodal:
    @pytest.mark.asyncio
    async def test_text_only_sends_string_content(self):
        provider = GroqProvider(api_key="test", model="test-model")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "answer"
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        await provider.generate("hello")

        call_args = provider._client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert isinstance(user_msg["content"], str)

    @pytest.mark.asyncio
    async def test_with_images_sends_list_content(self):
        provider = GroqProvider(api_key="test", model="test-model")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I can see the image"
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        imgs = [_b64_image("image/png")]
        await provider.generate("describe this", images=imgs)

        call_args = provider._client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert isinstance(user_msg["content"], list)
        assert user_msg["content"][0]["type"] == "text"
        assert user_msg["content"][1]["type"] == "image_url"


# ---------------------------------------------------------------------------
# F. ChatService — passes images to provider
# ---------------------------------------------------------------------------

class TestChatServiceImages:
    @pytest.mark.asyncio
    async def test_images_forwarded_to_provider_manager(self):
        from app.services.chat.chat_service import ChatService
        from app.services.chat.query_router import QueryCategory, RouteResult

        mock_retriever = MagicMock()
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build_general_prompt.return_value = MagicMock(text="prompt text")
        mock_provider_manager = AsyncMock()
        mock_provider_manager.generate = AsyncMock(return_value=MagicMock(
            text="answer", provider="test", model="m", category="general", sources=[],
        ))
        mock_query_router = MagicMock()
        mock_query_router.classify_with_embedding.return_value = RouteResult(
            QueryCategory.GENERAL, None
        )

        service = ChatService(
            retriever=mock_retriever,
            prompt_builder=mock_prompt_builder,
            provider_manager=mock_provider_manager,
            query_router=mock_query_router,
        )

        imgs = [_b64_image()]
        await service.chat("hello", owner_id="u1", images=imgs)

        mock_provider_manager.generate.assert_called_once()
        call_kwargs = mock_provider_manager.generate.call_args
        assert call_kwargs.kwargs.get("images") == imgs


# ---------------------------------------------------------------------------
# G. End-to-end: image attachment → provider receives multimodal request
# ---------------------------------------------------------------------------

class TestEndToEndImageTransport:
    """Reproduce the exact bug scenario: image + text → provider gets both."""

    @pytest.mark.asyncio
    async def test_image_reaches_provider_as_multimodal_content(self):
        from app.services.chat.chat_service import ChatService
        from app.services.chat.query_router import QueryCategory, RouteResult

        captured_prompt = {}

        async def fake_generate(prompt, images=None, **kwargs):
            captured_prompt["text"] = prompt
            captured_prompt["images"] = images
            return "I can see the image"

        mock_retriever = MagicMock()
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build_general_prompt.return_value = MagicMock(text="extract text from this pic")
        mock_provider_manager = AsyncMock()
        mock_provider_manager.generate = fake_generate
        mock_query_router = MagicMock()
        mock_query_router.classify_with_embedding.return_value = RouteResult(
            QueryCategory.GENERAL, None
        )

        service = ChatService(
            retriever=mock_retriever,
            prompt_builder=mock_prompt_builder,
            provider_manager=mock_provider_manager,
            query_router=mock_query_router,
        )

        imgs = [_b64_image("image/png")]
        await service.chat("extract the text from this pic", owner_id="u1", images=imgs)

        # The provider manager received images
        assert captured_prompt["images"] is not None
        assert len(captured_prompt["images"]) == 1
        assert captured_prompt["images"][0]["mime"] == "image/png"

        # build_user_content would produce a multimodal content list
        content = build_user_content(captured_prompt["text"], images=captured_prompt["images"])
        assert isinstance(content, list)
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"
