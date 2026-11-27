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
from querivue_agent.providers.openrouter import OpenRouterProvider
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
                credential_env="OPENROUTER_API_KEY",
                route_policy=RoleRoutePolicy(role="entry", route_ids=["openrouter_default"]),
            ),
            "supervisor": RoleModelConfig(
                credential_env="OPENROUTER_API_KEY",
                route_policy=RoleRoutePolicy(role="supervisor", route_ids=["openrouter_default"]),
            ),
            "sql": RoleModelConfig(
                credential_env="OPENROUTER_API_KEY",
                route_policy=RoleRoutePolicy(role="sql", route_ids=["openrouter_default"]),
            ),
            "python": RoleModelConfig(
                credential_env="OPENROUTER_API_KEY",
                route_policy=RoleRoutePolicy(role="python", route_ids=["openrouter_default"]),
            ),
            "answer": RoleModelConfig(
                credential_env="OPENROUTER_API_KEY",
                route_policy=RoleRoutePolicy(role="answer", route_ids=["openrouter_default"]),
            ),
            "reviewer": RoleModelConfig(
                credential_env="OPENROUTER_API_KEY",
                route_policy=RoleRoutePolicy(role="reviewer", route_ids=["openrouter_default"]),
            ),
            "clarification": RoleModelConfig(
                credential_env="OPENROUTER_API_KEY",
                route_policy=RoleRoutePolicy(role="clarification", route_ids=["openrouter_default"]),
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
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        yield
        os.environ.pop("OPENROUTER_API_KEY", None)

    def test_get_provider_openrouter(self) -> None:
        """_get_provider should create OpenRouterProvider."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        with patch("querivue_agent.providers.openrouter.ChatOpenRouter"):
            provider = gateway._get_provider("openrouter_default")
            assert isinstance(provider, OpenRouterProvider)

    def test_get_provider_caches_instances(self) -> None:
        """_get_provider should cache provider instances."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        with patch("querivue_agent.providers.openrouter.ChatOpenRouter"):
            p1 = gateway._get_provider("openrouter_default")
            p2 = gateway._get_provider("openrouter_default")
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
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        yield
        os.environ.pop("OPENROUTER_API_KEY", None)

    def test_get_model_for_role_entry(self) -> None:
        """_get_model_for_role should resolve entry correctly."""
        config = create_test_config()
        gateway = create_model_gateway(config)
        with patch("querivue_agent.providers.openrouter.ChatOpenRouter"):
            provider, model_id, settings = gateway._get_model_for_role("entry")

            assert isinstance(provider, OpenRouterProvider)
            assert model_id == "google/gemini-3.5-flash-lite"
            assert settings.reasoning == "minimal"
            assert settings.temperature == 0.0


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


class TestModelGatewayCallModel:
    """Tests for call_model method."""

    @pytest.fixture(autouse=True)
    def set_env(self) -> None:
        """Set required environment variables for provider creation."""
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        yield
        os.environ.pop("OPENROUTER_API_KEY", None)

    @pytest.mark.asyncio
    async def test_call_model_invokes_provider(self) -> None:
        """call_model should invoke provider.generate with correct args."""
        config = create_test_config()
        gateway = create_model_gateway(config)

        mock_provider = AsyncMock(spec=ModelProvider)
        mock_provider.provider_identity = ProviderIdentity(
            provider="openrouter",
            model_id="google/gemini-3.5-flash-lite",
            endpoint="https://openrouter.ai/api/v1",
            route="/v1/chat/completions",
            account_tier="paid",
            region="us-central1",
            quota_identity="default",
            sdk_name="langchain-openrouter",
            sdk_version="0.3.0",
            protocol_version="1.0",
            tokenizer_version="1.0",
            tokenizer_build_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            rate_manifest_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            observed_revision="unknown",
            max_context_tokens=128000,
            rates=[
                CostRate(meter="input_token", unit_size=1000, usd_per_unit="0.001"),
                CostRate(meter="output_token", unit_size=1000, usd_per_unit="0.002"),
            ],
            free_tier_enforced=False,
            accounting_verified=True,
            privacy_verified=False,
        )
        mock_response = ModelResponse(
            content="test response",
            tool_calls=None,
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            raw_response=None,
        )
        mock_provider.generate = AsyncMock(return_value=mock_response)

        gateway._providers["openrouter_default:google/gemini-3.5-flash-lite"] = mock_provider

        response = await gateway.call_model(
            role="supervisor",
            messages=[{"role": "user", "content": "test"}],
            invocation_id="inv-123",
        )

        mock_provider.generate.assert_called_once()
        call_args = mock_provider.generate.call_args
        request = call_args[0][0]
        assert request.messages == [{"role": "user", "content": "test"}]
        assert request.metadata["role"] == "supervisor"
        assert response == mock_response


class TestModelConfigDataclass:
    """Tests for ModelConfig dataclass."""

    def test_model_config_creation(self) -> None:
        """ModelConfig should store all fields."""
        config = ModelConfig(
            provider="openrouter",
            model_id="google/gemini-3.5-flash-lite",
            reasoning="low",
            temperature=0.0,
            max_tokens=8192,
        )
        assert config.provider == "openrouter"
        assert config.model_id == "google/gemini-3.5-flash-lite"
        assert config.reasoning == "low"
        assert config.temperature == 0.0
        assert config.max_tokens == 8192


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
