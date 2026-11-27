"""Model gateway integration with provider adapters and prompt management."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from querivue_agent.config import RunConfig
from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings
from querivue_agent.runtime.prompts import PromptBundle, load_prompt_bundle_v3, RoleName, assemble_role_prompt
from querivue_agent.providers.base import ModelProvider, ModelRequest, ModelResponse
from querivue_agent.providers.google import GoogleProvider
from querivue_agent.providers.nvidia import NVIDIAProvider
from querivue_agent.providers.openrouter import OpenRouterProvider
from querivue_agent.providers.cloudflare import CloudflareProvider
from querivue_agent.providers.ollama import OllamaProvider
from querivue_agent.providers.ollama_cloud import OllamaCloudProvider
from querivue_agent.runtime.credentials import OllamaCredentialPool, CredentialEntry


@dataclass(frozen=True)
class ModelConfig:
    """Model configuration for a role."""
    provider: Literal["google", "nvidia", "openrouter", "cloudflare", "ollama", "ollama_cloud"]
    model_id: str
    reasoning: Literal["minimal", "low", "medium", "high"] = "low"
    temperature: float = 0.0
    max_tokens: int = 8192


class ModelGateway:
    """Central gateway for model calls with provider abstraction and routing."""

    def __init__(
        self,
        config: RunConfig,
        trace_recorder=None,
    ) -> None:
        self._config = config
        self._providers: dict[str, ModelProvider] = {}
        self._prompt_bundle = load_prompt_bundle_v3()
        self._trace_recorder = trace_recorder
        self._credential_pool: OllamaCredentialPool | None = None

    def _get_provider(self, route_id: str, model_id: str | None = None) -> ModelProvider:
        """Get or create a provider instance for a route."""
        cache_key = f"{route_id}:{model_id or 'default'}"
        if cache_key in self._providers:
            return self._providers[cache_key]

        route = self._config.routes.get(route_id)
        if not route:
            raise ValueError(f"Route not found: {route_id}")

        provider: ModelProvider
        if route.transport == "google":
            provider = GoogleProvider()
        elif route.transport == "nvidia":
            provider = NVIDIAProvider()
        elif route.transport == "openrouter":
            cred = self._config.route_credential(route_id) if hasattr(self._config, 'route_credential') else None
            api_key = cred.get_secret_value() if cred else None
            provider = OpenRouterProvider(
                api_key=api_key,
                base_url=route.base_url,
                model_id=model_id or route.remote_model_id,
                provider_order=route.openrouter_provider_order,
                provider_only=route.openrouter_provider_only,
                disable_shared_capacity=route.openrouter_disable_shared_capacity,
            )
        elif route.transport == "cloudflare":
            provider = CloudflareProvider()
        elif route.transport == "ollama":
            provider = OllamaProvider(model_id=model_id or route.remote_model_id)
        elif route.transport == "ollama_cloud":
            # Initialize credential pool if needed
            if self._credential_pool is None:
                self._init_credential_pool()
            if self._credential_pool is None:
                raise RuntimeError("No Ollama Cloud credentials configured")
            # Use synchronous acquire to avoid asyncio.run nesting issues and improve performance
            cred_id, api_key = self._credential_pool.acquire_sync()
            provider = OllamaCloudProvider(
                api_key=api_key,
                base_url=route.base_url,
                model_id=model_id or route.remote_model_id,
            )
            # Store credential_id for error handling
            provider._credential_id = cred_id  # type: ignore
            provider._credential_pool = self._credential_pool  # type: ignore
        else:
            raise ValueError(f"Unknown transport: {route.transport}")

        self._providers[cache_key] = provider
        return provider

    def _init_credential_pool(self) -> None:
        """Initialize the Ollama Cloud credential pool from config."""
        credentials = []
        for cred_id, cred_ref in self._config.credentials.items():
            if cred_ref.quota_group.startswith("ollama"):
                api_key = self._config.route_credential(cred_id)
                if api_key:
                    credentials.append(CredentialEntry(
                        credential_id=cred_id,
                        api_key=api_key.get_secret_value(),
                        priority=cred_ref.priority,
                        quota_group=cred_ref.quota_group,
                        enabled=cred_ref.enabled,
                    ))
        if credentials:
            self._credential_pool = OllamaCredentialPool(credentials)

    def _get_model_for_role(self, role: RoleName) -> tuple[ModelProvider, str, InferenceSettings]:
        """Get provider, model ID, and inference settings for a role."""
        model_config = self._config.models.get(role)
        if not model_config:
            raise ValueError(f"No model configured for role: {role}")

        route_policy = model_config.route_policy
        if not route_policy:
            raise ValueError(f"No route policy for role: {role}")

        # In pinned mode, use first route; in resilient mode, iterate through routes
        route_id = route_policy.route_ids[0]
        route = self._config.routes.get(route_id)
        if not route:
            raise ValueError(f"Route not found: {route_id}")

        model_id = route.remote_model_id

        provider = self._get_provider(route_id, model_id)

        # Configure inference settings based on role
        if role in ("entry", "clarification"):
            reasoning = "minimal"
            temperature = 0.0
        else:
            reasoning = "low"
            temperature = 0.0

        # Use role-specific inference settings if provided, else defaults
        if model_config.inference:
            settings = model_config.inference
        else:
            settings = InferenceSettings(
                reasoning=reasoning,
                temperature=temperature,
                seed=42,
                max_generated_tokens=8192,
                sampling_overrides_verified=True,
                reasoning_in_output_budget=True,
            )

        return provider, model_id, settings

    def _config_role_to_prompt_role(self, role: str) -> RoleName:
        """Map config role names to prompt role names."""
        mapping = {
            "entry": "entry_assessor",
            "supervisor": "supervisor",
            "sql": "sql_specialist",
            "python": "python_specialist",
            "answer": "answer_specialist",
            "reviewer": "reviewer",
            "clarification": "clarification_agent",
        }
        return mapping.get(role, role)  # type: ignore[return-value]

    def get_prompt(self, role: RoleName) -> str:
        """Get assembled prompt for a role (common + role-specific)."""
        prompt_role = self._config_role_to_prompt_role(role)
        return self._prompt_bundle.assemble(prompt_role)

    def get_prompt_bundle(self) -> PromptBundle:
        """Get the full prompt bundle."""
        return self._prompt_bundle

    async def call_model(
        self,
        role: RoleName,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | Literal["auto", "none"] | None = None,
        system_instruction: str | None = None,
        generation_config: dict[str, Any] | None = None,
        invocation_id: str | None = None,
    ) -> ModelResponse:
        """Call a model for a specific role with routing and fallback support."""
        model_config = self._config.models.get(role)
        if not model_config:
            raise ValueError(f"No model configured for role: {role}")

        route_policy = model_config.route_policy
        if not route_policy or route_policy.pinned_mode:
            # Pinned mode: single route, no fallback
            route_id = route_policy.route_ids[0] if route_policy and route_policy.route_ids else None
            return await self._call_with_route(role, messages, tools, tool_choice, system_instruction, generation_config, invocation_id, route_id)

        # Resilient mode: try routes in order
        last_error = None
        for i, route_id in enumerate(route_policy.route_ids):
            try:
                return await self._call_with_route(role, messages, tools, tool_choice, system_instruction, generation_config, invocation_id, route_id)
            except Exception as e:
                last_error = e
                # Record error for Ollama credential pool
                await self._record_route_error(route_id, e)
                if i < len(route_policy.route_ids) - 1:
                    continue
        raise last_error or RuntimeError("All routes exhausted")

    async def _call_with_route(
        self,
        role: RoleName,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: dict[str, Any] | Literal["auto", "none"] | None,
        system_instruction: str | None,
        generation_config: dict[str, Any] | None,
        invocation_id: str | None,
        route_id: str | None,
    ) -> ModelResponse:
        """Call model using a specific route."""
        if route_id is None:
            raise ValueError("Route ID required")

        route = self._config.routes.get(route_id)
        if not route:
            raise ValueError(f"Route not found: {route_id}")

        model_config = self._config.models.get(role)
        if not model_config:
            raise ValueError(f"No model configured for role: {role}")

        model_id = route.remote_model_id
        provider = self._get_provider(route_id, model_id)

        prompt = self.get_prompt(role)

        # Build request
        request = ModelRequest(
            messages=messages,
            system_instruction=system_instruction or prompt,
            tools=tools,
            tool_choice=tool_choice,
            generation_config=generation_config,
            metadata={"role": role, "model_id": model_id, "invocation_id": invocation_id, "route_id": route_id},
        )

        # Record model call in trace
        if self._trace_recorder and invocation_id:
            self._trace_recorder.record_model_call(
                invocation_id=invocation_id,
                provider=provider.provider_identity,
                settings=model_config.inference or InferenceSettings(
                    reasoning="low",
                    temperature=0.0,
                    seed=42,
                    max_generated_tokens=8192,
                    sampling_overrides_verified=True,
                    reasoning_in_output_budget=True,
                ),
                messages=messages,
                tools=tools or [],
                system_instruction=system_instruction or prompt,
            )

        # Call the model
        import time
        start = time.time()
        try:
            response = await provider.generate(request, model_config.inference or InferenceSettings(
                reasoning="low",
                temperature=0.0,
                seed=42,
                max_generated_tokens=8192,
                sampling_overrides_verified=True,
                reasoning_in_output_budget=True,
            ))
            duration_ms = int((time.time() - start) * 1000)

            # Record success for Ollama credential pool
            if hasattr(provider, '_credential_id') and hasattr(provider, '_credential_pool'):
                await provider._credential_pool.record_success(provider._credential_id)  # type: ignore

            # Record model response in trace
            if self._trace_recorder and invocation_id:
                self._trace_recorder.record_model_response(
                    invocation_id=invocation_id,
                    response_content=response.content,
                    tool_calls=response.tool_calls,
                    usage=response.usage,
                    duration_ms=duration_ms,
                    cost_usd="0.00",  # Would calculate from usage and rates
                )

            return response
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)

            # Record error for Ollama credential pool
            if hasattr(provider, '_credential_id') and hasattr(provider, '_credential_pool'):
                await provider._credential_pool.record_error(provider._credential_id, status_code=getattr(e, 'response', {}).status_code if hasattr(e, 'response') else None)  # type: ignore

            if self._trace_recorder and invocation_id:
                self._trace_recorder.record_error(
                    invocation_id=invocation_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            raise

    async def _record_route_error(self, route_id: str, error: Exception) -> None:
        """Record error for route-specific handling (e.g., Ollama credential pool)."""
        route = self._config.routes.get(route_id)
        if route and route.transport == "ollama_cloud" and self._credential_pool:
            # Find credential ID for this route
            for cred_id, cred_ref in self._config.credentials.items():
                if cred_ref.quota_group.startswith("ollama"):
                    status_code = getattr(error, 'response', {}).status_code if hasattr(error, 'response') else None
                    await self._credential_pool.record_error(cred_id, status_code=status_code)
                    break

    async def close(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()


def create_model_gateway(
    config: RunConfig,
    trace_recorder=None,
) -> ModelGateway:
    """Create a model gateway with the specified configuration."""
    return ModelGateway(config=config, trace_recorder=trace_recorder)