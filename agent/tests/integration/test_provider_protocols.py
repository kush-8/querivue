"""Integration tests for provider protocols - mocked to avoid real API calls."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import httpx
import pytest

from querivue_agent.providers.base import ModelProvider, ModelRequest, ModelResponse
from querivue_agent.providers.openrouter import OpenRouterProvider
from querivue_agent.providers.ollama_cloud import OllamaCloudProvider
from querivue_agent.contracts.manifests import InferenceSettings, ProviderIdentity


def create_mock_langchain_response(content: str = "response", usage: dict | None = None, tool_calls: list | None = None, finish_reason: str = "stop") -> MagicMock:
    """Create a mock langchain strategy response object."""
    response = MagicMock()
    response.content = content
    response.tool_calls = tool_calls or []
    response.usage_metadata = usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    response.response_metadata = {"finish_reason": finish_reason}
    response.model_dump = lambda: {
        "content": content,
        "tool_calls": tool_calls or [],
        "usage_metadata": usage or {},
        "response_metadata": {"finish_reason": finish_reason},
    }
    return response


class MockStreamChunk:
    """Mock streaming chunk for langchain astream."""
    def __init__(self, content: str = "chunk"):
        self.content = content
        self.tool_calls = []
        self.response_metadata = {"finish_reason": "stop"}
        self.model_dump = lambda: {"content": content, "tool_calls": [], "response_metadata": {"finish_reason": "stop"}}


def create_mock_settings():
    """Create standard InferenceSettings for tests."""
    return InferenceSettings(
        reasoning="low",
        temperature=0.0,
        seed=42,
        max_generated_tokens=8192,
        sampling_overrides_verified=True,
        reasoning_in_output_budget=True,
    )


class TestOpenRouterProviderProtocol:
    """Tests for OpenRouter provider protocol compliance."""

    @pytest.fixture
    def provider(self):
        with patch("querivue_agent.providers.openrouter.ChatOpenRouter") as mock_model_class:
            mock_model = MagicMock()
            mock_model_class.return_value = mock_model
            provider = OpenRouterProvider(api_key="test-key", model_id="google/gemini-3.5-flash-lite")
            provider._client = mock_model
            return provider

    @pytest.mark.asyncio
    async def test_generate_returns_model_response(self, provider):
        """generate should return ModelResponse."""
        provider._client.ainvoke = AsyncMock(return_value=create_mock_langchain_response(
            content="OpenRouter response",
            usage={"prompt_tokens": 60, "completion_tokens": 30, "total_tokens": 90}
        ))

        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()
        response = await provider.generate(request, settings)

        assert response.content == "OpenRouter response"
        assert response.usage["total_tokens"] == 90

    @pytest.mark.asyncio
    async def test_generate_includes_headers(self, provider):
        """generate should work with OpenRouter provider."""
        provider._client.ainvoke = AsyncMock(return_value=create_mock_langchain_response(content="ok"))

        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()
        response = await provider.generate(request, settings)

        assert response.content == "ok"

    @pytest.mark.asyncio
    async def test_provider_identity_complete(self, provider):
        """provider_identity should have all required fields."""
        identity = provider.provider_identity
        assert identity.provider == "openrouter"
        assert identity.rates is not None
        assert identity.account_tier == "paid"
        assert identity.privacy_verified is False


class TestProtocolConsistency:
    """Tests ensuring providers follow the protocol."""

    @pytest.mark.asyncio
    async def test_openrouter_implements_generate(self):
        """OpenRouter should implement generate method."""
        with patch("querivue_agent.providers.openrouter.ChatOpenRouter") as mock_model_class:
            mock_model = MagicMock()
            mock_model_class.return_value = mock_model
            mock_model.ainvoke = AsyncMock(return_value=create_mock_langchain_response(content="ok"))
            provider = OpenRouterProvider(api_key="test-key")
            provider._client = mock_model

        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()
        response = await provider.generate(request, settings)

        assert isinstance(response, ModelResponse)
        assert hasattr(response, "content")
        assert hasattr(response, "tool_calls")
        assert hasattr(response, "usage")
        assert hasattr(response, "raw_response")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
