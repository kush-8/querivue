"""Integration tests for provider protocols - mocked to avoid real API calls."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from querivue_agent.providers.base import ModelProvider, ModelRequest, ModelResponse
from querivue_agent.providers.google import GoogleProvider
from querivue_agent.providers.nvidia import NVIDIAProvider
from querivue_agent.providers.openrouter import OpenRouterProvider
from querivue_agent.providers.cloudflare import CloudflareProvider
from querivue_agent.contracts.manifests import InferenceSettings, ProviderIdentity


class MockAsyncClient:
    """Mock httpx.AsyncClient for testing."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.last_request = None

    async def post(self, url, **kwargs):
        self.call_count += 1
        self.last_request = {"url": url, "kwargs": kwargs}
        if self.responses:
            response = self.responses.pop(0)
        else:
            response = MagicMock()
            response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "default"}]}, "finishReason": "STOP"}]}
            response.raise_for_status = MagicMock()
        return response

    def stream(self, method, url, **kwargs):
        self.call_count += 1
        self.last_request = {"url": url, "method": method, "kwargs": kwargs}

        class MockStream:
            def __init__(self, chunks):
                self.chunks = chunks
                self.idx = 0

            async def aiter_lines(self):
                for chunk in self.chunks:
                    yield chunk
                yield "data: [DONE]"

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        chunks = getattr(self, 'last_stream_chunks', [b'data: {"candidates": [{"content": {"parts": [{"text": "chunk"}]}]}]'])
        return MockStream(chunks)

    async def aclose(self):
        pass


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


class TestGoogleProviderProtocol:
    """Tests for Google provider protocol compliance."""

    @pytest.fixture
    def mock_client(self):
        return MockAsyncClient()

    @pytest.fixture
    def provider(self, mock_client):
        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = GoogleProvider(api_key="test-key", model_id="gemini-3.8-flash")
            provider._client = mock_client
            return provider

    @pytest.mark.asyncio
    async def test_generate_returns_model_response(self, provider):
        """generate should return ModelResponse with required fields."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {
                    "candidates": [{
                        "content": {"parts": [{"text": "Hello world"}]},
                        "finishReason": "STOP"
                    }],
                    "usageMetadata": {
                        "promptTokenCount": 100,
                        "candidatesTokenCount": 50,
                        "totalTokenCount": 150,
                    }
                },
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()
        response = await provider.generate(request, settings)

        assert isinstance(response, ModelResponse)
        assert response.content == "Hello world"
        assert response.usage == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        assert response.raw_response is not None

    @pytest.mark.asyncio
    async def test_generate_with_tools(self, provider):
        """generate should handle tool calls in response."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {
                    "candidates": [{
                        "content": {"parts": [{
                            "functionCall": {"name": "test_tool", "args": {"param": "value"}}
                        }]},
                        "finishReason": "STOP"
                    }]
                },
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "test_tool", "parameters": {}}}],
        )
        settings = create_mock_settings()
        response = await provider.generate(request, settings)

        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["function"]["name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_generate_handles_empty_candidates(self, provider):
        """generate should handle empty candidates gracefully."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {"candidates": []},
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()
        response = await provider.generate(request, settings)

        assert response.content is None
        assert response.tool_calls is None
        assert response.usage is None

    @pytest.mark.asyncio
    async def test_generate_system_instruction(self, provider):
        """generate should include system_instruction in request."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]},
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(
            messages=[{"role": "user", "content": "test"}],
            system_instruction="You are a helpful assistant",
        )
        settings = create_mock_settings()
        await provider.generate(request, settings)

        # Verify system instruction was sent
        call_kwargs = provider._client.last_request["kwargs"]
        assert "json" in call_kwargs
        body = call_kwargs["json"]
        assert "systemInstruction" in body
        assert body["systemInstruction"]["parts"][0]["text"] == "You are a helpful assistant"

    @pytest.mark.asyncio
    async def test_generate_stream_yields_responses(self, provider):
        """generate_stream should yield ModelResponse chunks."""
        chunks = [
            'data: {"candidates": [{"content": {"parts": [{"text": "chunk1"}]}}]}',
            'data: {"candidates": [{"content": {"parts": [{"text": "chunk2"}]}}]}',
        ]
        provider._client.responses = [MagicMock()]  # Not used for stream
        provider._client = MockAsyncClient()
        provider._client.responses = []

        # Use the built-in MockStream from MockAsyncClient
        chunks = [
            'data: {"candidates": [{"content": {"parts": [{"text": "chunk1"}]}}]}',
            'data: {"candidates": [{"content": {"parts": [{"text": "chunk2"}]}}]}',
        ]
        provider._client.last_stream_chunks = chunks

        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()

        responses = []
        async for resp in provider.generate_stream(request, settings):
            responses.append(resp)

        assert len(responses) == 2
        assert all(isinstance(r, ModelResponse) for r in responses)

    @pytest.mark.asyncio
    async def test_provider_identity_complete(self, provider):
        """provider_identity should have all required fields."""
        identity = provider.provider_identity
        assert isinstance(identity, ProviderIdentity)
        assert identity.provider == "google"
        assert identity.model_id == "gemini-3.8-flash"
        assert identity.endpoint == "https://generativelanguage.googleapis.com"
        assert identity.rates is not None
        assert len(identity.rates) == 2

    @pytest.mark.asyncio
    async def test_close_closes_client(self, provider):
        """close should close the httpx client."""
        await provider.close()
        # Client close was called - verified by no exception


class TestNVIDIAProviderProtocol:
    """Tests for NVIDIA provider protocol compliance."""

    @pytest.fixture
    def provider(self):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MockAsyncClient()
            mock_client_class.return_value = mock_client
            provider = NVIDIAProvider(api_key="test-key", model_id="qwen/qwen3-next-80b-a3b-instruct")
            provider._client = mock_client
            return provider

    @pytest.mark.asyncio
    async def test_generate_returns_model_response(self, provider):
        """generate should return ModelResponse with required fields."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {
                    "choices": [{
                        "message": {"content": "NVIDIA response", "tool_calls": None},
                        "finish_reason": "stop"
                    }],
                    "usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120}
                },
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()
        response = await provider.generate(request, settings)

        assert isinstance(response, ModelResponse)
        assert response.content == "NVIDIA response"
        assert response.usage == {"input_tokens": 80, "output_tokens": 40, "total_tokens": 120}

    @pytest.mark.asyncio
    async def test_generate_with_tool_calls(self, provider):
        """generate should handle tool calls."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {
                    "choices": [{
                        "message": {
                            "content": None,
                            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "tool", "arguments": '{"x":1}'}}]
                        },
                        "finish_reason": "tool_calls"
                    }],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80}
                },
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "tool", "parameters": {}}}],
            tool_choice="auto",
        )
        settings = create_mock_settings()
        response = await provider.generate(request, settings)

        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["function"]["name"] == "tool"

    @pytest.mark.asyncio
    async def test_generate_system_instruction_prepended(self, provider):
        """generate should prepend system instruction to messages."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(
            messages=[{"role": "user", "content": "test"}],
            system_instruction="System prompt",
        )
        settings = create_mock_settings()
        await provider.generate(request, settings)

        call_kwargs = provider._client.last_request["kwargs"]
        body = call_kwargs["json"]
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "System prompt"
        assert body["messages"][1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_provider_identity_complete(self, provider):
        """provider_identity should have all required fields."""
        identity = provider.provider_identity
        assert identity.provider == "nvidia"
        assert identity.model_id == "qwen/qwen3-next-80b-a3b-instruct"
        assert identity.rates is not None
        assert identity.free_tier_enforced is True


class TestOpenRouterProviderProtocol:
    """Tests for OpenRouter provider protocol compliance."""

    @pytest.fixture
    def provider(self):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MockAsyncClient()
            mock_client_class.return_value = mock_client
            provider = OpenRouterProvider(api_key="test-key", model_id="google/gemini-3.5-flash-lite")
            provider._client = mock_client
            return provider

    @pytest.mark.asyncio
    async def test_generate_returns_model_response(self, provider):
        """generate should return ModelResponse."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {
                    "choices": [{
                        "message": {"content": "OpenRouter response"},
                        "finish_reason": "stop"
                    }],
                    "usage": {"prompt_tokens": 60, "completion_tokens": 30, "total_tokens": 90}
                },
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()
        response = await provider.generate(request, settings)

        assert response.content == "OpenRouter response"
        assert response.usage["total_tokens"] == 90

    @pytest.mark.asyncio
    async def test_generate_includes_headers(self, provider):
        """generate should include OpenRouter-specific headers."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()
        await provider.generate(request, settings)

        call_kwargs = provider._client.last_request["kwargs"]
        assert "headers" in call_kwargs
        headers = call_kwargs["headers"]
        assert "Authorization" in headers
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers
        assert headers["X-Title"] == "Querivue Agent"

    @pytest.mark.asyncio
    async def test_provider_identity_complete(self, provider):
        """provider_identity should have all required fields."""
        identity = provider.provider_identity
        assert identity.provider == "openrouter"
        assert identity.rates is not None
        assert identity.account_tier == "paid"
        assert identity.privacy_verified is False


class TestCloudflareProviderProtocol:
    """Tests for Cloudflare provider protocol compliance."""

    @pytest.fixture
    def provider(self):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MockAsyncClient()
            mock_client_class.return_value = mock_client
            provider = CloudflareProvider(
                account_id="test-account",
                api_token="test-token",
                model_id="@cf/meta/llama-3.3-70b-instruct-fp8-fast"
            )
            provider._client = mock_client
            return provider

    @pytest.mark.asyncio
    async def test_generate_returns_model_response(self, provider):
        """generate should return ModelResponse."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {
                    "result": {
                        "response": "Cloudflare response",
                        "usage": {"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60}
                    }
                },
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()
        response = await provider.generate(request, settings)

        assert response.content == "Cloudflare response"
        assert response.usage == {"input_tokens": 40, "output_tokens": 20, "total_tokens": 60}
        assert response.tool_calls is None  # Cloudflare doesn't support tools

    @pytest.mark.asyncio
    async def test_generate_system_instruction_included(self, provider):
        """generate should include system instruction in messages."""
        provider._client.responses = [
            MagicMock(
                json=lambda: {"result": {"response": "ok"}},
                raise_for_status=MagicMock()
            )
        ]

        request = ModelRequest(
            messages=[{"role": "user", "content": "test"}],
            system_instruction="System prompt",
        )
        settings = create_mock_settings()
        await provider.generate(request, settings)

        call_kwargs = provider._client.last_request["kwargs"]
        body = call_kwargs["json"]
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "System prompt"

    @pytest.mark.asyncio
    async def test_provider_identity_complete(self, provider):
        """provider_identity should have all required fields."""
        identity = provider.provider_identity
        assert identity.provider == "cloudflare"
        assert identity.account_tier == "free"
        assert identity.rates is not None


class TestProviderErrorHandling:
    """Tests for provider error handling."""

    @pytest.fixture
    def failing_provider(self):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MockAsyncClient()
            mock_client_class.return_value = mock_client
            # Make post raise an error
            mock_client.post = AsyncMock(side_effect=httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=MagicMock(),
                response=MagicMock(status_code=429)
            ))
            provider = GoogleProvider(api_key="test-key")
            provider._client = mock_client
            return provider

    @pytest.mark.asyncio
    async def test_generate_propagates_http_errors(self, failing_provider):
        """generate should propagate HTTP errors."""
        request = ModelRequest(messages=[{"role": "user", "content": "test"}])
        settings = create_mock_settings()

        with pytest.raises(httpx.HTTPStatusError):
            await failing_provider.generate(request, settings)

    @pytest.mark.asyncio
    async def test_generate_handles_timeout(self):
        """generate should handle timeout errors."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MockAsyncClient()
            mock_client_class.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Request timeout"))

            provider = GoogleProvider(api_key="test-key")
            provider._client = mock_client

            request = ModelRequest(messages=[{"role": "user", "content": "test"}])
            settings = create_mock_settings()

            with pytest.raises(httpx.TimeoutException):
                await provider.generate(request, settings)

    @pytest.mark.asyncio
    async def test_generate_handles_malformed_response(self):
        """generate should handle malformed JSON response."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MockAsyncClient()
            mock_client_class.return_value = mock_client
            mock_client.responses = [
                MagicMock(
                    json=lambda: {"not": "expected structure"},
                    raise_for_status=MagicMock()
                )
            ]

            provider = GoogleProvider(api_key="test-key")
            provider._client = mock_client

            request = ModelRequest(messages=[{"role": "user", "content": "test"}])
            settings = create_mock_settings()
            response = await provider.generate(request, settings)

            # Should handle gracefully - empty candidates
            assert response.content is None


class TestProviderTokenCounting:
    """Tests for provider token counting behavior."""

    def test_default_token_counting(self):
        """Default count_tokens should use character heuristic."""
        with patch("httpx.AsyncClient"):
            provider = GoogleProvider(api_key="test-key")
            count = provider.count_tokens("Hello world")
            assert count == len("Hello world") // 4

    def test_token_counting_used_for_admission(self):
        """Token counting should be available for budget admission."""
        # This test documents that token counting is used by the gateway
        # for preflight admission checks
        with patch("httpx.AsyncClient"):
            provider = GoogleProvider(api_key="test-key")
            assert hasattr(provider, "count_tokens")
            assert callable(provider.count_tokens)


class TestProtocolConsistency:
    """Tests ensuring all providers follow the same protocol."""

    @pytest.fixture(params=["google", "nvidia", "openrouter", "cloudflare"])
    def provider_name(self, request):
        return request.param

    @pytest.mark.asyncio
    async def test_all_providers_implement_generate(self, provider_name):
        """All providers should implement generate method."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MockAsyncClient()
            mock_client_class.return_value = mock_client

            if provider_name == "google":
                provider = GoogleProvider(api_key="test-key")
            elif provider_name == "nvidia":
                provider = NVIDIAProvider(api_key="test-key")
            elif provider_name == "openrouter":
                provider = OpenRouterProvider(api_key="test-key")
            elif provider_name == "cloudflare":
                provider = CloudflareProvider(account_id="test", api_token="test")

            provider._client = mock_client

            # Mock a minimal successful response
            if provider_name == "cloudflare":
                mock_client.responses = [
                    MagicMock(json=lambda: {"result": {"response": "ok"}}, raise_for_status=MagicMock())
                ]
            elif provider_name == "google":
                mock_client.responses = [
                    MagicMock(json=lambda: {"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]}, raise_for_status=MagicMock())
                ]
            else:
                mock_client.responses = [
                    MagicMock(json=lambda: {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}, raise_for_status=MagicMock())
                ]

            request = ModelRequest(messages=[{"role": "user", "content": "test"}])
            settings = create_mock_settings()
            response = await provider.generate(request, settings)

            assert isinstance(response, ModelResponse)
            assert hasattr(response, "content")
            assert hasattr(response, "tool_calls")
            assert hasattr(response, "usage")
            assert hasattr(response, "raw_response")

    @pytest.mark.asyncio
    async def test_all_providers_implement_generate_stream(self, provider_name):
        """All providers should implement generate_stream method."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MockAsyncClient()
            mock_client_class.return_value = mock_client

            if provider_name == "google":
                provider = GoogleProvider(api_key="test-key")
            elif provider_name == "nvidia":
                provider = NVIDIAProvider(api_key="test-key")
            elif provider_name == "openrouter":
                provider = OpenRouterProvider(api_key="test-key")
            elif provider_name == "cloudflare":
                provider = CloudflareProvider(account_id="test", api_token="test")

            provider._client = mock_client

            # Stream just needs to not crash
            request = ModelRequest(messages=[{"role": "user", "content": "test"}])
            settings = create_mock_settings()

            # Just verify method exists and is callable
            assert hasattr(provider, "generate_stream")
            assert callable(provider.generate_stream)

    @pytest.mark.asyncio
    async def test_all_providers_have_provider_identity(self, provider_name):
        """All providers should have provider_identity property."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MockAsyncClient()
            mock_client_class.return_value = mock_client

            if provider_name == "google":
                provider = GoogleProvider(api_key="test-key")
            elif provider_name == "nvidia":
                provider = NVIDIAProvider(api_key="test-key")
            elif provider_name == "openrouter":
                provider = OpenRouterProvider(api_key="test-key")
            elif provider_name == "cloudflare":
                provider = CloudflareProvider(account_id="test", api_token="test")

            provider._client = mock_client

            identity = provider.provider_identity
            assert isinstance(identity, ProviderIdentity)
            assert identity.provider == provider_name
            assert identity.model_id is not None
            assert identity.rates is not None
            assert identity.max_context_tokens > 0

    @pytest.mark.asyncio
    async def test_all_providers_implement_close(self, provider_name):
        """All providers should implement close method."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MockAsyncClient()
            mock_client_class.return_value = mock_client

            if provider_name == "google":
                provider = GoogleProvider(api_key="test-key")
            elif provider_name == "nvidia":
                provider = NVIDIAProvider(api_key="test-key")
            elif provider_name == "openrouter":
                provider = OpenRouterProvider(api_key="test-key")
            elif provider_name == "cloudflare":
                provider = CloudflareProvider(account_id="test", api_token="test")

            provider._client = mock_client

            assert hasattr(provider, "close")
            assert callable(provider.close)
            await provider.close()  # Should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])