"""Unit tests for ModelGateway and provider integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import os

import pytest

from querivue_agent.runtime.models import (
    ModelGateway,
    FREE_DEVELOPMENT_CONFIGS,
    MODEL_ALLOCATIONS,
    create_model_gateway,
    ModelConfig,
)
from querivue_agent.runtime.prompts import RoleName, load_prompt_bundle_v3
from querivue_agent.providers.base import ModelProvider, ModelRequest, ModelResponse
from querivue_agent.providers.google import GoogleProvider
from querivue_agent.providers.nvidia import NVIDIAProvider
from querivue_agent.providers.openrouter import OpenRouterProvider
from querivue_agent.providers.cloudflare import CloudflareProvider
from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings, CostRate


class TestModelConfigs:
    """Tests for model configuration constants."""

    def test_f1_config_has_all_roles(self) -> None:
        """F1 config should have provider for all 8 roles."""
        f1 = FREE_DEVELOPMENT_CONFIGS["F1"]
        expected_roles = {
            "entry_assessor",
            "clarification_agent",
            "supervisor",
            "sql_specialist",
            "python_specialist",
            "answer_specialist",
            "reviewer",
        }
        assert set(f1.keys()) == expected_roles
        assert all(v == "google" for v in f1.values())

    def test_f2_config_has_reviewer_on_nvidia(self) -> None:
        """F2 config should use NVIDIA for reviewer."""
        f2 = FREE_DEVELOPMENT_CONFIGS["F2"]
        assert f2["reviewer"] == "nvidia"
        assert f2["entry_assessor"] == "google"

    def test_f3_config_all_cloudflare(self) -> None:
        """F3 config should use Cloudflare for all roles."""
        f3 = FREE_DEVELOPMENT_CONFIGS["F3"]
        assert all(v == "cloudflare" for v in f3.values())

    def test_model_allocations_have_models(self) -> None:
        """MODEL_ALLOCATIONS should have models for each provider."""
        assert "google" in MODEL_ALLOCATIONS
        assert "nvidia" in MODEL_ALLOCATIONS
        assert "cloudflare" in MODEL_ALLOCATIONS
        assert "entry_assessor" in MODEL_ALLOCATIONS["google"]
        assert "reviewer" in MODEL_ALLOCATIONS["nvidia"]
        assert "all" in MODEL_ALLOCATIONS["cloudflare"]


class TestModelGatewayInit:
    """Tests for ModelGateway initialization."""

    def test_create_model_gateway_default_f1(self) -> None:
        """create_model_gateway should default to F1 config."""
        gateway = create_model_gateway()
        assert gateway._config_name == "F1"
        assert gateway._config == FREE_DEVELOPMENT_CONFIGS["F1"]

    def test_create_model_gateway_f2(self) -> None:
        """create_model_gateway should accept F2 config."""
        gateway = create_model_gateway(config_name="F2")
        assert gateway._config_name == "F2"
        assert gateway._config == FREE_DEVELOPMENT_CONFIGS["F2"]

    def test_create_model_gateway_f3(self) -> None:
        """create_model_gateway should accept F3 config."""
        gateway = create_model_gateway(config_name="F3")
        assert gateway._config_name == "F3"
        assert gateway._config == FREE_DEVELOPMENT_CONFIGS["F3"]

    def test_invalid_config_raises(self) -> None:
        """Invalid config name should raise ValueError."""
        with pytest.raises(KeyError):
            create_model_gateway(config_name="INVALID")  # type: ignore[arg-type]

    def test_model_gateway_loads_prompt_bundle(self) -> None:
        """ModelGateway should load v3 prompt bundle on init."""
        gateway = create_model_gateway()
        bundle = gateway.get_prompt_bundle()
        assert bundle.bundle_version == "querivue-roles-v3"
        assert len(bundle._role_prompts) == 9


class TestModelGatewayProviderCreation:
    """Tests for provider instantiation."""

    @pytest.fixture(autouse=True)
    def set_env(self) -> None:
        """Set required environment variables for provider creation."""
        os.environ["GOOGLE_API_KEY"] = "test-key"
        os.environ["NVIDIA_API_KEY"] = "test-key"
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        os.environ["CLOUDFLARE_API_TOKEN"] = "test-token"
        os.environ["CLOUDFLARE_ACCOUNT_ID"] = "test-account"
        yield
        # Cleanup
        for key in ["GOOGLE_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]:
            os.environ.pop(key, None)

    def test_get_provider_google(self) -> None:
        """_get_provider should create GoogleProvider."""
        gateway = create_model_gateway()
        provider = gateway._get_provider("google")
        assert isinstance(provider, GoogleProvider)

    def test_get_provider_nvidia(self) -> None:
        """_get_provider should create NVIDIAProvider."""
        gateway = create_model_gateway()
        provider = gateway._get_provider("nvidia")
        assert isinstance(provider, NVIDIAProvider)

    def test_get_provider_openrouter(self) -> None:
        """_get_provider should create OpenRouterProvider."""
        gateway = create_model_gateway()
        provider = gateway._get_provider("openrouter")
        assert isinstance(provider, OpenRouterProvider)

    def test_get_provider_cloudflare(self) -> None:
        """_get_provider should create CloudflareProvider."""
        gateway = create_model_gateway()
        provider = gateway._get_provider("cloudflare")
        assert isinstance(provider, CloudflareProvider)

    def test_get_provider_caches_instances(self) -> None:
        """_get_provider should cache provider instances."""
        gateway = create_model_gateway()
        p1 = gateway._get_provider("google")
        p2 = gateway._get_provider("google")
        assert p1 is p2

    def test_unknown_provider_raises(self) -> None:
        """Unknown provider name should raise ValueError."""
        gateway = create_model_gateway()
        with pytest.raises(ValueError, match="Unknown provider"):
            gateway._get_provider("unknown")


class TestModelGatewayRoleResolution:
    """Tests for role-to-model resolution."""

    @pytest.fixture(autouse=True)
    def set_env(self) -> None:
        """Set required environment variables for provider creation."""
        os.environ["GOOGLE_API_KEY"] = "test-key"
        os.environ["NVIDIA_API_KEY"] = "test-key"
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        os.environ["CLOUDFLARE_API_TOKEN"] = "test-token"
        os.environ["CLOUDFLARE_ACCOUNT_ID"] = "test-account"
        yield
        # Cleanup
        for key in ["GOOGLE_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]:
            os.environ.pop(key, None)

    def test_get_model_for_role_entry_assessor(self) -> None:
        """_get_model_for_role should resolve entry_assessor correctly."""
        gateway = create_model_gateway("F1")
        provider, model_id, settings = gateway._get_model_for_role("entry_assessor")

        assert isinstance(provider, GoogleProvider)
        assert model_id == "gemini-3.5-flash-lite"
        assert settings.reasoning == "minimal"
        assert settings.temperature == 0.0

    def test_get_model_for_role_sql_specialist(self) -> None:
        """_get_model_for_role should resolve sql_specialist correctly."""
        gateway = create_model_gateway("F1")
        provider, model_id, settings = gateway._get_model_for_role("sql_specialist")

        assert isinstance(provider, GoogleProvider)
        assert model_id == "gemini-3.8-flash"
        assert settings.reasoning == "low"
        assert settings.temperature == 0.0

    def test_get_model_for_role_reviewer_f1(self) -> None:
        """_get_model_for_role should resolve reviewer correctly for F1."""
        gateway = create_model_gateway("F1")
        provider, model_id, settings = gateway._get_model_for_role("reviewer")

        assert isinstance(provider, GoogleProvider)
        assert model_id == "gemini-3.8-flash"

    def test_get_model_for_role_reviewer_f2(self) -> None:
        """_get_model_for_role should resolve reviewer to NVIDIA for F2."""
        gateway = create_model_gateway("F2")
        provider, model_id, settings = gateway._get_model_for_role("reviewer")

        assert isinstance(provider, NVIDIAProvider)
        assert model_id == "qwen/qwen3-next-80b-a3b-instruct"

    def test_get_model_for_role_cloudflare_f3(self) -> None:
        """_get_model_for_role should use Cloudflare 'all' model for F3."""
        gateway = create_model_gateway("F3")
        provider, model_id, settings = gateway._get_model_for_role("supervisor")

        assert isinstance(provider, CloudflareProvider)
        assert model_id == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


class TestModelGatewayPromptAssembly:
    """Tests for prompt assembly through gateway."""

    def test_get_prompt_returns_assembled(self) -> None:
        """get_prompt should return assembled prompt (common + role)."""
        gateway = create_model_gateway()
        prompt = gateway.get_prompt("sql_specialist")

        bundle = load_prompt_bundle_v3()
        expected = bundle.assemble("sql_specialist")
        assert prompt == expected

    def test_get_prompt_bundle_returns_bundle(self) -> None:
        """get_prompt_bundle should return the PromptBundle."""
        gateway = create_model_gateway()
        bundle = gateway.get_prompt_bundle()
        assert isinstance(bundle, type(load_prompt_bundle_v3()))
        assert bundle.bundle_version == "querivue-roles-v3"


class TestModelGatewayCallModel:
    """Tests for call_model method."""

    @pytest.fixture(autouse=True)
    def set_env(self) -> None:
        """Set required environment variables for provider creation."""
        os.environ["GOOGLE_API_KEY"] = "test-key"
        os.environ["NVIDIA_API_KEY"] = "test-key"
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        os.environ["CLOUDFLARE_API_TOKEN"] = "test-token"
        os.environ["CLOUDFLARE_ACCOUNT_ID"] = "test-account"
        yield
        # Cleanup
        for key in ["GOOGLE_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]:
            os.environ.pop(key, None)

    @pytest.mark.asyncio
    async def test_call_model_invokes_provider(self) -> None:
        """call_model should invoke provider.generate with correct args."""
        gateway = create_model_gateway()

        # Mock provider
        mock_provider = AsyncMock(spec=ModelProvider)
        mock_provider.provider_identity = ProviderIdentity(
            provider="google",
            model_id="gemini-3.8-flash",
            endpoint="https://generativelanguage.googleapis.com",
            route="/v1/models/gemini-3.8-flash:generateContent",
            account_tier="paid",
            region="us-central1",
            quota_identity="default",
            sdk_name="google-generativeai",
            sdk_version="0.3.0",
            protocol_version="1.0",
            tokenizer_version="1.0",
            tokenizer_build_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            rate_manifest_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            observed_revision="unknown",
            max_context_tokens=1000000,
            rates=[
                CostRate(meter="input_token", unit_size=1000, usd_per_unit="0.001"),
                CostRate(meter="output_token", unit_size=1000, usd_per_unit="0.002"),
            ],
            free_tier_enforced=True,
            accounting_verified=True,
            privacy_verified=True,
        )
        mock_response = ModelResponse(
            content="test response",
            tool_calls=None,
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            raw_response=None,
        )
        mock_provider.generate = AsyncMock(return_value=mock_response)

        gateway._providers["google"] = mock_provider

        # Call model
        response = await gateway.call_model(
            role="supervisor",
            messages=[{"role": "user", "content": "test"}],
            invocation_id="inv-123",
        )

        # Verify provider was called
        mock_provider.generate.assert_called_once()
        call_args = mock_provider.generate.call_args
        # request is passed as first positional argument
        request = call_args[0][0]
        assert request.messages == [{"role": "user", "content": "test"}]
        assert request.metadata["role"] == "supervisor"
        assert request.metadata["invocation_id"] == "inv-123"
        assert response == mock_response

    @pytest.mark.asyncio
    async def test_call_model_with_tools(self) -> None:
        """call_model should pass tools and tool_choice to provider."""
        gateway = create_model_gateway()
        mock_provider = AsyncMock(spec=ModelProvider)
        mock_provider.provider_identity = ProviderIdentity(
            provider="google",
            model_id="gemini-3.8-flash",
            endpoint="https://generativelanguage.googleapis.com",
            route="/v1/models/gemini-3.8-flash:generateContent",
            account_tier="paid",
            region="us-central1",
            quota_identity="default",
            sdk_name="google-generativeai",
            sdk_version="0.3.0",
            protocol_version="1.0",
            tokenizer_version="1.0",
            tokenizer_build_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            rate_manifest_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            observed_revision="unknown",
            max_context_tokens=1000000,
            rates=[
                CostRate(meter="input_token", unit_size=1000, usd_per_unit="0.001"),
                CostRate(meter="output_token", unit_size=1000, usd_per_unit="0.002"),
            ],
            free_tier_enforced=True,
            accounting_verified=True,
            privacy_verified=True,
        )
        mock_response = ModelResponse(
            content=None,
            tool_calls=[{"id": "call_1", "name": "test_tool", "arguments": {}}],
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            raw_response=None,
        )
        mock_provider.generate = AsyncMock(return_value=mock_response)
        gateway._providers["google"] = mock_provider

        tools = [{"name": "test_tool", "description": "Test", "parameters": {}}]
        response = await gateway.call_model(
            role="sql_specialist",
            messages=[{"role": "user", "content": "test"}],
            tools=tools,
            tool_choice="auto",
            invocation_id="inv-456",
        )

        call_args = mock_provider.generate.call_args
        request = call_args[0][0]
        assert request.tools == tools
        assert request.tool_choice == "auto"

    @pytest.mark.asyncio
    async def test_call_model_with_system_instruction(self) -> None:
        """call_model should pass system_instruction to provider."""
        gateway = create_model_gateway()
        mock_provider = AsyncMock(spec=ModelProvider)
        mock_provider.provider_identity = ProviderIdentity(
            provider="google",
            model_id="gemini-3.8-flash",
            endpoint="https://generativelanguage.googleapis.com",
            route="/v1/models/gemini-3.8-flash:generateContent",
            account_tier="paid",
            region="us-central1",
            quota_identity="default",
            sdk_name="google-generativeai",
            sdk_version="0.3.0",
            protocol_version="1.0",
            tokenizer_version="1.0",
            tokenizer_build_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            rate_manifest_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            observed_revision="unknown",
            max_context_tokens=1000000,
            rates=[
                CostRate(meter="input_token", unit_size=1000, usd_per_unit="0.001"),
                CostRate(meter="output_token", unit_size=1000, usd_per_unit="0.002"),
            ],
            free_tier_enforced=True,
            accounting_verified=True,
            privacy_verified=True,
        )
        mock_response = ModelResponse(
            content="response",
            tool_calls=None,
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            raw_response=None,
        )
        mock_provider.generate = AsyncMock(return_value=mock_response)
        gateway._providers["google"] = mock_provider

        custom_system = "Custom system instruction"
        await gateway.call_model(
            role="entry_assessor",
            messages=[],
            system_instruction=custom_system,
            invocation_id="inv-789",
        )

        call_args = mock_provider.generate.call_args
        request = call_args[0][0]
        assert request.system_instruction == custom_system

    @pytest.mark.asyncio
    async def test_call_model_records_trace_on_success(self) -> None:
        """call_model should record trace events on success."""
        mock_trace = MagicMock()
        gateway = create_model_gateway(trace_recorder=mock_trace)
        mock_provider = AsyncMock(spec=ModelProvider)
        mock_provider.provider_identity = ProviderIdentity(
            provider="google",
            model_id="gemini-3.8-flash",
            endpoint="https://generativelanguage.googleapis.com",
            route="/v1/models/gemini-3.8-flash:generateContent",
            account_tier="paid",
            region="us-central1",
            quota_identity="default",
            sdk_name="google-generativeai",
            sdk_version="0.3.0",
            protocol_version="1.0",
            tokenizer_version="1.0",
            tokenizer_build_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            rate_manifest_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            observed_revision="unknown",
            max_context_tokens=1000000,
            rates=[
                CostRate(meter="input_token", unit_size=1000, usd_per_unit="0.001"),
                CostRate(meter="output_token", unit_size=1000, usd_per_unit="0.002"),
            ],
            free_tier_enforced=True,
            accounting_verified=True,
            privacy_verified=True,
        )
        mock_response = ModelResponse(
            content="test",
            tool_calls=None,
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            raw_response=None,
        )
        mock_provider.generate = AsyncMock(return_value=mock_response)
        gateway._providers["google"] = mock_provider

        await gateway.call_model(
            role="supervisor",
            messages=[{"role": "user", "content": "test"}],
            invocation_id="inv-trace",
        )

        # Verify trace calls
        assert mock_trace.record_model_call.called
        assert mock_trace.record_model_response.called
        # Check model_call payload
        call_args = mock_trace.record_model_call.call_args
        assert call_args[1]["invocation_id"] == "inv-trace"
        assert call_args[1]["provider"].provider == "google"

    @pytest.mark.asyncio
    async def test_call_model_records_trace_on_error(self) -> None:
        """call_model should record trace error on provider failure."""
        mock_trace = MagicMock()
        gateway = create_model_gateway(trace_recorder=mock_trace)
        mock_provider = AsyncMock(spec=ModelProvider)
        mock_provider.provider_identity = ProviderIdentity(
            provider="google",
            model_id="gemini-3.8-flash",
            endpoint="https://generativelanguage.googleapis.com",
            route="/v1/models/gemini-3.8-flash:generateContent",
            account_tier="paid",
            region="us-central1",
            quota_identity="default",
            sdk_name="google-generativeai",
            sdk_version="0.3.0",
            protocol_version="1.0",
            tokenizer_version="1.0",
            tokenizer_build_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            rate_manifest_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            observed_revision="unknown",
            max_context_tokens=1000000,
            rates=[
                CostRate(meter="input_token", unit_size=1000, usd_per_unit="0.001"),
                CostRate(meter="output_token", unit_size=1000, usd_per_unit="0.002"),
            ],
            free_tier_enforced=True,
            accounting_verified=True,
            privacy_verified=True,
        )
        mock_provider.generate = AsyncMock(side_effect=Exception("Provider error"))
        gateway._providers["google"] = mock_provider

        with pytest.raises(Exception, match="Provider error"):
            await gateway.call_model(
                role="supervisor",
                messages=[],
                invocation_id="inv-error",
            )

        assert mock_trace.record_error.called
        error_args = mock_trace.record_error.call_args
        assert error_args[1]["invocation_id"] == "inv-error"
        assert error_args[1]["error_type"] == "Exception"

    @pytest.mark.asyncio
    async def test_call_model_unknown_role_raises(self) -> None:
        """call_model with unknown role should raise ValueError."""
        gateway = create_model_gateway()
        with pytest.raises(ValueError, match="No provider configured"):
            await gateway.call_model(
                role="unknown_role",  # type: ignore[arg-type]
                messages=[],
            )


class TestModelGatewayClose:
    """Tests for gateway cleanup."""

    @pytest.mark.asyncio
    async def test_close_closes_all_providers(self) -> None:
        """close should call close on all cached providers."""
        gateway = create_model_gateway()
        mock_google = AsyncMock(spec=GoogleProvider)
        mock_nvidia = AsyncMock(spec=NVIDIAProvider)
        gateway._providers = {"google": mock_google, "nvidia": mock_nvidia}

        await gateway.close()

        mock_google.close.assert_called_once()
        mock_nvidia.close.assert_called_once()
        assert gateway._providers == {}


class TestModelConfigDataclass:
    """Tests for ModelConfig dataclass."""

    def test_model_config_creation(self) -> None:
        """ModelConfig should store all fields."""
        config = ModelConfig(
            provider="google",
            model_id="gemini-3.8-flash",
            reasoning="low",
            temperature=0.0,
            max_tokens=8192,
        )
        assert config.provider == "google"
        assert config.model_id == "gemini-3.8-flash"
        assert config.reasoning == "low"
        assert config.temperature == 0.0
        assert config.max_tokens == 8192

    def test_model_config_defaults(self) -> None:
        """ModelConfig should have correct defaults."""
        config = ModelConfig(provider="google", model_id="test")
        assert config.reasoning == "low"
        assert config.temperature == 0.0
        assert config.max_tokens == 8192


if __name__ == "__main__":
    pytest.main([__file__, "-v"])