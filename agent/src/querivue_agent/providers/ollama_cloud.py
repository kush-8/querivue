"""Ollama Cloud provider adapter using langchain-ollama."""

from __future__ import annotations

import json
import os
from typing import Any, AsyncGenerator

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage

from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings, CostRate
from .base import ModelProvider, ModelRequest, ModelResponse


class OllamaCloudProvider(ModelProvider):
    """Ollama Cloud model provider adapter using langchain-ollama."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://ollama.com/v1",
        model_id: str = "llama3.1:70b",
    ) -> None:
        self._api_key = api_key or os.getenv("OLLAMA_API_KEY") or os.getenv("OLLAMA_CLOUD_API_KEY")
        if not self._api_key:
            raise ValueError("OLLAMA_API_KEY or OLLAMA_CLOUD_API_KEY not set")
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id

        # Configure ChatOllama with custom base_url and auth via sync_client_kwargs
        # langchain-ollama parses auth from URL or sync_client_kwargs headers
        auth_url = f"https://{self._api_key}:@{self._base_url.replace('https://', '')}"
        self._client = ChatOllama(
            model=model_id,
            base_url=self._base_url,
            sync_client_kwargs={"headers": {"Authorization": f"Bearer {self._api_key}"}},
            async_client_kwargs={"headers": {"Authorization": f"Bearer {self._api_key}"}},
        )

    @property
    def provider_identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider="ollama_cloud",
            model_id=self._model_id,
            endpoint=self._base_url,
            route="/v1/chat/completions",
            account_tier="paid",
            region="global",
            quota_identity="ollama_cloud",
            sdk_name="langchain-ollama",
            sdk_version="0.3.0",
            protocol_version="1.0",
            tokenizer_version="1.0",
            tokenizer_build_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            rate_manifest_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            observed_revision="unknown",
            max_context_tokens=128000,
            rates=[
                CostRate(meter="input_token", unit_size=1000, usd_per_unit="0.15"),
                CostRate(meter="output_token", unit_size=1000, usd_per_unit="0.60"),
            ],
            free_tier_enforced=False,
            accounting_verified=False,
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
                # Handle tool messages
                result.append(HumanMessage(content=content, additional_kwargs={"role": "tool"}))
        return result

    async def generate(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ) -> ModelResponse:
        """Generate a response from Ollama Cloud."""
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
    ) -> AsyncGenerator[ModelResponse, None]:
        """Generate a streaming response from Ollama Cloud."""
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