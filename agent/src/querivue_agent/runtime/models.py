"""Model gateway integration with provider adapters and prompt management."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings
from querivue_agent.runtime.prompts import PromptBundle, load_prompt_bundle_v3, RoleName, assemble_role_prompt
from querivue_agent.providers.base import ModelProvider, ModelRequest, ModelResponse
from querivue_agent.providers.google import GoogleProvider
from querivue_agent.providers.nvidia import NVIDIAProvider
from querivue_agent.providers.openrouter import OpenRouterProvider
from querivue_agent.providers.cloudflare import CloudflareProvider


# Configuration constants (from role-prompts-models.md)
FREE_DEVELOPMENT_CONFIGS = {
    "F1": {
        "entry_assessor": "google",
        "clarification_agent": "google",
        "supervisor": "google",
        "sql_specialist": "google",
        "python_specialist": "google",
        "answer_specialist": "google",
        "reviewer": "google",
    },
    "F2": {
        "entry_assessor": "google",
        "clarification_agent": "google",
        "supervisor": "google",
        "sql_specialist": "google",
        "python_specialist": "google",
        "answer_specialist": "google",
        "reviewer": "nvidia",
    },
    "F3": {
        "entry_assessor": "cloudflare",
        "clarification_agent": "cloudflare",
        "supervisor": "cloudflare",
        "sql_specialist": "cloudflare",
        "python_specialist": "cloudflare",
        "answer_specialist": "cloudflare",
        "reviewer": "cloudflare",
    },
}

MODEL_ALLOCATIONS = {
    "google": {
        "entry_assessor": "gemini-3.5-flash-lite",
        "clarification_agent": "gemini-3.5-flash-lite",
        "supervisor": "gemini-3.8-flash",
        "sql_specialist": "gemini-3.8-flash",
        "python_specialist": "gemini-3.8-flash",
        "answer_specialist": "gemini-3.8-flash",
        "reviewer": "gemini-3.8-flash",
    },
    "nvidia": {
        "reviewer": "qwen/qwen3-next-80b-a3b-instruct",
    },
    "cloudflare": {
        "all": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    },
}


@dataclass(frozen=True)
class ModelConfig:
    """Model configuration for a role."""
    provider: Literal["google", "nvidia", "openrouter", "cloudflare"]
    model_id: str
    reasoning: Literal["minimal", "low", "medium", "high"] = "low"
    temperature: float = 0.0
    max_tokens: int = 8192


class ModelGateway:
    """Central gateway for model calls with provider abstraction."""

    def __init__(
        self,
        config_name: Literal["F1", "F2", "F3"] = "F1",
        trace_recorder=None,
    ) -> None:
        self._config_name = config_name
        self._config = FREE_DEVELOPMENT_CONFIGS[config_name]
        self._providers: dict[str, ModelProvider] = {}
        self._prompt_bundle = load_prompt_bundle_v3()
        self._trace_recorder = trace_recorder

    def _get_provider(self, provider_name: str) -> ModelProvider:
        """Get or create a provider instance."""
        if provider_name in self._providers:
            return self._providers[provider_name]

        if provider_name == "google":
            provider = GoogleProvider()
        elif provider_name == "nvidia":
            provider = NVIDIAProvider()
        elif provider_name == "openrouter":
            provider = OpenRouterProvider()
        elif provider_name == "cloudflare":
            provider = CloudflareProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

        self._providers[provider_name] = provider
        return provider

    def _get_model_for_role(self, role: RoleName) -> tuple[ModelProvider, str, InferenceSettings]:
        """Get provider, model ID, and inference settings for a role."""
        provider_name = self._config.get(role)
        if not provider_name:
            raise ValueError(f"No provider configured for role: {role}")

        provider = self._get_provider(provider_name)
        model_id = MODEL_ALLOCATIONS[provider_name].get(role)
        if not model_id:
            model_id = MODEL_ALLOCATIONS[provider_name].get("all", "unknown")

        # Configure inference settings based on role
        if role in ("entry_assessor", "clarification_agent"):
            reasoning = "minimal"
            temperature = 0.0
        else:
            reasoning = "low"
            temperature = 0.0

        settings = InferenceSettings(
            reasoning=reasoning,
            temperature=temperature,
            seed=42,
            max_generated_tokens=8192,
            sampling_overrides_verified=True,
            reasoning_in_output_budget=True,
        )

        return provider, model_id, settings

    def get_prompt(self, role: RoleName) -> str:
        """Get assembled prompt for a role (common + role-specific)."""
        return self._prompt_bundle.assemble(role)

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
        """Call a model for a specific role."""
        provider, model_id, settings = self._get_model_for_role(role)
        prompt = self.get_prompt(role)

        # Build request
        request = ModelRequest(
            messages=messages,
            system_instruction=system_instruction or prompt,
            tools=tools,
            tool_choice=tool_choice,
            generation_config=generation_config,
            metadata={"role": role, "model_id": model_id, "invocation_id": invocation_id},
        )

        # Record model call in trace
        if self._trace_recorder and invocation_id:
            self._trace_recorder.record_model_call(
                invocation_id=invocation_id,
                provider=provider.provider_identity,
                settings=settings,
                messages=messages,
                tools=tools or [],
                system_instruction=system_instruction or prompt,
            )

        # Call the model
        import time
        start = time.time()
        try:
            response = await provider.generate(request, settings)
            duration_ms = int((time.time() - start) * 1000)

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
            if self._trace_recorder and invocation_id:
                self._trace_recorder.record_error(
                    invocation_id=invocation_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            raise

    async def close(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()


def create_model_gateway(
    config_name: Literal["F1", "F2", "F3"] = "F1",
    trace_recorder=None,
) -> ModelGateway:
    """Create a model gateway with the specified configuration."""
    return ModelGateway(config_name=config_name, trace_recorder=trace_recorder)