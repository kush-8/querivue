"""OpenRouter provider adapter using langchain-openrouter."""

from __future__ import annotations

import os
from typing import Any

from langchain_openrouter import ChatOpenRouter
from langchain_core.messages import HumanMessage, AIMessage

from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings, CostRate
from .base import ModelProvider, ModelRequest, ModelResponse


class OpenRouterProvider(ModelProvider):
    """OpenRouter API provider adapter using langchain-openrouter with BYOK support."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        model_id: str = "google/gemini-3.5-flash-lite",
        # BYOK and provider selection controls
        provider_order: list[str] | None = None,
        provider_only: list[str] | None = None,
        disable_shared_capacity: bool = True,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._provider_order = provider_order or []
        self._provider_only = provider_only or []
        self._disable_shared_capacity = disable_shared_capacity

        # Build provider parameter for langchain-openrouter
        provider_param: dict[str, Any] = {}
        if self._provider_order:
            provider_param["order"] = self._provider_order
        if self._provider_only:
            provider_param["only"] = self._provider_only
        if self._disable_shared_capacity:
            provider_param["allow_fallbacks"] = False

        # Create langchain model
        self._client = ChatOpenRouter(
            model=model_id,
            api_key=self._api_key,
            base_url=self._base_url,
            openrouter_provider=provider_param if provider_param else None,
        )

    @property
    def provider_identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider="openrouter",
            model_id=self._model_id,
            endpoint=self._base_url,
            route="/v1/chat/completions",
            account_tier="paid",
            region="global",
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
                CostRate(meter="input_token", unit_size=1000, usd_per_unit="0.30"),
                CostRate(meter="output_token", unit_size=1000, usd_per_unit="2.50"),
            ],
            free_tier_enforced=False,
            accounting_verified=True,
            privacy_verified=False,
        )

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[HumanMessage | AIMessage]:
        """Convert dict messages to langchain message objects."""
        result = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                result.append(HumanMessage(content=content, additional_kwargs={"role": "system"}))
            elif role == "user":
                result.append(HumanMessage(content=content))
            elif role == "assistant":
                result.append(AIMessage(content=content))
            elif role == "tool":
                result.append(HumanMessage(content=content, additional_kwargs={"role": "tool"}))
        return result

    async def generate(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ) -> ModelResponse:
        """Generate a response from OpenRouter."""
        messages = request.messages.copy()
        if request.system_instruction:
            messages.insert(0, {"role": "system", "content": request.system_instruction})

        lc_messages = self._convert_messages(messages)

        # Build kwargs for langchain
        kwargs: dict[str, Any] = {}
        if inference_settings.temperature is not None:
            kwargs["temperature"] = inference_settings.temperature
        if inference_settings.max_generated_tokens is not None:
            kwargs["max_tokens"] = inference_settings.max_generated_tokens
        if inference_settings.seed is not None:
            kwargs["seed"] = inference_settings.seed

        response = await self._client.ainvoke(lc_messages, **kwargs)

        return ModelResponse(
            content=response.content,
            tool_calls=response.tool_calls,
            usage=getattr(response, 'usage_metadata', None),
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else str(response),
            provider_metadata={"finish_reason": response.response_metadata.get("finish_reason") if hasattr(response, 'response_metadata') else None},
        )

    async def generate_stream(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ):
        """Generate a streaming response from OpenRouter."""
        messages = request.messages.copy()
        if request.system_instruction:
            messages.insert(0, {"role": "system", "content": request.system_instruction})

        lc_messages = self._convert_messages(messages)

        # Build kwargs for langchain
        kwargs: dict[str, Any] = {}
        if inference_settings.temperature is not None:
            kwargs["temperature"] = inference_settings.temperature
        if inference_settings.max_generated_tokens is not None:
            kwargs["max_tokens"] = inference_settings.max_generated_tokens
        if inference_settings.seed is not None:
            kwargs["seed"] = inference_settings.seed

        async for chunk in self._client.astream(lc_messages, **kwargs):
            yield ModelResponse(
                content=chunk.content,
                tool_calls=chunk.tool_calls,
                usage=None,
                raw_response=chunk.model_dump() if hasattr(chunk, 'model_dump') else str(chunk),
                provider_metadata={"finish_reason": chunk.response_metadata.get("finish_reason") if hasattr(chunk, 'response_metadata') else None},
            )

    async def close(self) -> None:
        pass