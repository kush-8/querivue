"""Unit tests for ModelGateway and provider integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import os

import pytest

from querivue_agent.config import load_config, RunConfig, RoleModelConfig, RoleRoutePolicy, RouteConfig, CredentialReference
from querivue_agent.runtime.models import (
    ModelGateway,
    create_model_gateway,
    ModelConfig,
)
from querivue_agent.runtime.prompts import RoleName, load_prompt_bundle_v3
from querivue_agent.providers.base import ModelProvider, ModelRequest, ModelResponse
from querivue_agent.providers.google import GoogleProvider
from querivue_agent.providers.nvidia import NVIDIAProvider
from querivue_agent.providers.openrouter import OpenRouterProvider
from querivue_agent.providers.cloudflare import CloudflareProvider
from querivue_agent.providers.ollama_cloud import OllamaCloudProvider
from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings, CostRate


def create_test_config() -> RunConfig:
    """Create a minimal test RunConfig."""
    from querivue_agent.config import (
        RunLimits, RoleLimits, ContextLimits, ExecutionLimits, ReviewLimits,
        ROLE_SCOPES, ALL_ROLES, LocalBuildIdentity
    )
    from querivue_agent.contracts.evaluation import SpendCaps

    role_limits = {}
    for role in ALL_ROLES:
        role_limits[role] = RoleLimits(
            limit_scope=ROLE_SCOPES[role],
            request_input_tokens=8192,
            request_output_tokens=4096,
            cumulative_input_tokens=32768,
            cumulative_output_tokens=8192,
            logical_invocations=4,
            physical_requests=5,
            active_seconds=60,
            request_timeout_seconds=10,
        )

    return RunConfig(
        schema_version=1,
        profile="offline",
        live_enabled=False,
        run_limits=RunLimits(
            active_seconds=600,
            hard_wall_seconds=3600,
            input_tokens=1250000,
            output_tokens=190000,
            pending_tasks=4,
            actions_per_task=2,
            concurrent_actions=2,
            dispatch_attempts=8,
            review_passes=2,
            clarification_slots=2,
            deliberate_retries_per_action=1,
        ),
        role_limits=role_limits,
        context_limits=ContextLimits(
            thread_candidates=5,
            label_utf8_bytes=256,
            unanchored_candidates=1,
            optional_exchanges=2,
            entry_optional_tokens=1024,
            clarification_optional_tokens=1024,
            other_optional_tokens=2048,
            evidence_views=8,
            analysis_preview_rows=32,
            answer_preview_rows=128,
            preview_columns=32,
            charts=4,
            cell_utf8_bytes=2048,
            default_preview_rows=8,
            overflow_replans=2,
            compaction_trigger_percent=75,
            compaction_rebuilds=1,
        ),
        sql_limits=ExecutionLimits(
            max_model_requests=8,
            max_tool_calls=6,
            max_executions=4,
            max_corrections=2,
            max_terminal_corrections=1,
            max_transient_retries=1,
            no_progress_rounds=2,
            active_seconds=120,
            execution_seconds=30,
        ),
        python_limits=ExecutionLimits(
            max_model_requests=8,
            max_tool_calls=6,
            max_executions=4,
            max_corrections=2,
            max_terminal_corrections=1,
            max_transient_retries=1,
            no_progress_rounds=2,
            active_seconds=120,
            execution_seconds=30,
        ),
        review_limits=ReviewLimits(
            logical_passes=2,
            logical_per_pass=2,
            physical_per_pass=3,
            total_physical=5,
            total_logical=4,
            per_pass_seconds=30,
            total_seconds=60,
            request_timeout_seconds=20,
            finalization_seconds=5,
            max_findings=8,
            supports_per_finding=16,
            support_occurrences=64,
            block_ids_per_finding=16,
            text_utf8_bytes=1024,
            json_bytes=32768,
        ),
        spend_caps=SpendCaps(operator="0", project="0", intake="0", action="0", run="0", suite="0"),
        routes={
            "google_default": RouteConfig(
                route_id="google_default",
                transport="google",
                remote_model_id="gemini-3.8-flash",
                base_url="https://generativelanguage.googleapis.com",
                max_context_tokens=1000000,
                input_token_limit=100000,
                output_token_limit=100000,
            ),
            "nvidia_default": RouteConfig(
                route_id="nvidia_default",
                transport="nvidia",
                remote_model_id="qwen/qwen3-next-80b-a3b-instruct",
                base_url="https://integrate.api.nvidia.com/v1",
                max_context_tokens=128000,
                input_token_limit=100000,
                output_token_limit=100000,
            ),
            "openrouter_default": RouteConfig(
                route_id="openrouter_default",
                transport="openrouter",
                remote_model_id="google/gemini-3.5-flash-lite",
                base_url="https://openrouter.ai/api/v1",
                max_context_tokens=128000,
                input_token_limit=100000,
                output_token_limit=100000,
            ),
        },
        models={
            "entry": RoleModelConfig(
                credential_env="GOOGLE_API_KEY",
                route_policy=RoleRoutePolicy(role="entry", route_ids=["google_default"]),
            ),
            "supervisor": RoleModelConfig(
                credential_env="GOOGLE_API_KEY",
                route_policy=RoleRoutePolicy(role="supervisor", route_ids=["google_default"]),
            ),
            "sql": RoleModelConfig(
                credential_env="GOOGLE_API_KEY",
                route_policy=RoleRoutePolicy(role="sql", route_ids=["google_default"]),
            ),
            "python": RoleModelConfig(
                credential_env="GOOGLE_API_KEY",
                route_policy=RoleRoutePolicy(role="python", route_ids=["google_default"]),
            ),
            "answer": RoleModelConfig(
                credential_env="GOOGLE_API_KEY",
                route_policy=RoleRoutePolicy(role="answer", route_ids=["google_default"]),
            ),
            "reviewer": RoleModelConfig(
                credential_env="GOOGLE_API_KEY",
                route_policy=RoleRoutePolicy(role="reviewer", route_ids=["google_default"]),
            ),
            "clarification": RoleModelConfig(
                credential_env="GOOGLE_API_KEY",
                route_policy=RoleRoutePolicy(role="clarification", route_ids=["google_default"]),
            ),
        },
    )


class TestModelGatewayInit:
    """Tests for ModelGateway initialization."""

    def test_create_model_gateway_with_config(self) -> None:
        """create_model_gateway should accept RunConfig."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        assert gateway._config == config

    def test_model_gateway_loads_prompt_bundle(self) -> None:
        """ModelGateway should load v3 prompt bundle on init."""
        config = create_test_config()
        gateway = create_model_gateway(config)
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
        config = create_test_config()
        gateway = create_model_gateway(config)
        provider = gateway._get_provider("google_default")
        assert isinstance(provider, GoogleProvider)

    def test_get_provider_nvidia(self) -> None:
        """_get_provider should create NVIDIAProvider."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        provider = gateway._get_provider("nvidia_default")
        assert isinstance(provider, NVIDIAProvider)

    def test_get_provider_openrouter(self) -> None:
        """_get_provider should create OpenRouterProvider."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        provider = gateway._get_provider("openrouter_default")
        assert isinstance(provider, OpenRouterProvider)

    def test_get_provider_caches_instances(self) -> None:
        """_get_provider should cache provider instances."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        p1 = gateway._get_provider("google_default")
        p2 = gateway._get_provider("google_default")
        assert p1 is p2

    def test_unknown_provider_raises(self) -> None:
        """Unknown route ID should raise ValueError."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        with pytest.raises(ValueError, match="Route not found"):
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

    def test_get_model_for_role_entry(self) -> None:
        """_get_model_for_role should resolve entry correctly."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        provider, model_id, settings = gateway._get_model_for_role("entry")

        assert isinstance(provider, GoogleProvider)
        assert model_id == "gemini-3.8-flash"
        assert settings.reasoning == "minimal"
        assert settings.temperature == 0.0

    def test_get_model_for_role_sql(self) -> None:
        """_get_model_for_role should resolve sql correctly."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        provider, model_id, settings = gateway._get_model_for_role("sql")

        assert isinstance(provider, GoogleProvider)
        assert model_id == "gemini-3.8-flash"
        assert settings.reasoning == "low"
        assert settings.temperature == 0.0

    def test_get_model_for_role_reviewer(self) -> None:
        """_get_model_for_role should resolve reviewer correctly."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        provider, model_id, settings = gateway._get_model_for_role("reviewer")

        assert isinstance(provider, GoogleProvider)
        assert model_id == "gemini-3.8-flash"


class TestModelGatewayPromptAssembly:
    """Tests for prompt assembly through gateway."""

    def test_get_prompt_returns_assembled(self) -> None:
        """get_prompt should return assembled prompt (common + role)."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        prompt = gateway.get_prompt("sql_specialist")

        bundle = load_prompt_bundle_v3()
        expected = bundle.assemble("sql_specialist")
        assert prompt == expected

    def test_get_prompt_bundle_returns_bundle(self) -> None:
        """get_prompt_bundle should return the PromptBundle."""
        config = create_test_config()
        gateway = create_model_gateway(config)
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
        config = create_test_config()
        gateway = create_model_gateway(config)

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

        gateway._providers["google_default:gemini-3.8-flash"] = mock_provider

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
        config = create_test_config()
        gateway = create_model_gateway(config)
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
        gateway._providers["google_default:gemini-3.8-flash"] = mock_provider

        tools = [{"name": "test_tool", "description": "Test", "parameters": {}}]
        response = await gateway.call_model(
            role="sql",
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
        config = create_test_config()
        gateway = create_model_gateway(config)
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
        gateway._providers["google_default:gemini-3.8-flash"] = mock_provider

        custom_system = "Custom system instruction"
        await gateway.call_model(
            role="entry",
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
        config = create_test_config()
        mock_trace = MagicMock()
        gateway = create_model_gateway(config, trace_recorder=mock_trace)
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
        gateway._providers["google_default:gemini-3.8-flash"] = mock_provider

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
        config = create_test_config()
        mock_trace = MagicMock()
        gateway = create_model_gateway(config, trace_recorder=mock_trace)
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
        gateway._providers["google_default:gemini-3.8-flash"] = mock_provider

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
        config = create_test_config()
        gateway = create_model_gateway(config)
        with pytest.raises(ValueError, match="No model configured for role"):
            await gateway.call_model(
                role="unknown_role",  # type: ignore[arg-type]
                messages=[],
            )


class TestModelGatewayClose:
    """Tests for gateway cleanup."""

    @pytest.mark.asyncio
    async def test_close_closes_all_providers(self) -> None:
        """close should call close on all cached providers."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        mock_google = AsyncMock(spec=GoogleProvider)
        mock_nvidia = AsyncMock(spec=NVIDIAProvider)
        gateway._providers = {"google_default": mock_google, "nvidia_default": mock_nvidia}

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