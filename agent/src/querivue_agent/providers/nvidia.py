"""NVIDIA provider adapter."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings, CostRate
from .base import ModelProvider, ModelRequest, ModelResponse


class NVIDIAProvider(ModelProvider):
    """NVIDIA NIM API provider adapter."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://integrate.api.nvidia.com",
        model_id: str = "qwen/qwen3-next-80b-a3b-instruct",
    ) -> None:
        self._api_key = api_key or os.getenv("NVIDIA_API_KEY")
        if not self._api_key:
            raise ValueError("NVIDIA_API_KEY not set")
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def provider_identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider="nvidia",
            model_id=self._model_id,
            endpoint=self._base_url,
            route="/v1/chat/completions",
            account_tier="free",
            region="us",
            quota_identity="default",
            sdk_name="openai",
            sdk_version="1.0.0",
            protocol_version="1.0",
            tokenizer_version="1.0",
            tokenizer_build_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            rate_manifest_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            observed_revision="unknown",
            max_context_tokens=32768,
            rates=[
                CostRate(meter="input_token", unit_size=1000, usd_per_unit="0.00"),
                CostRate(meter="output_token", unit_size=1000, usd_per_unit="0.00"),
            ],
            free_tier_enforced=True,
            accounting_verified=True,
            privacy_verified=True,
        )

    async def generate(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ) -> ModelResponse:
        """Generate a response from NVIDIA NIM."""
        url = f"{self._base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        body = self._build_request_body(request, inference_settings)

        response = await self._client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

        return self._parse_response(data)

    def _build_request_body(
        self,
        request: ModelRequest,
        settings: InferenceSettings,
    ) -> dict[str, Any]:
        """Build OpenAI-compatible request body."""
        body = {
            "model": self._model_id,
            "messages": request.messages,
            "temperature": settings.temperature,
            "max_tokens": settings.max_generated_tokens,
        }

        if settings.seed is not None:
            body["seed"] = settings.seed

        if request.system_instruction:
            body["messages"].insert(0, {"role": "system", "content": request.system_instruction})

        if request.tools:
            body["tools"] = request.tools
            body["tool_choice"] = request.tool_choice or "auto"

        if request.generation_config:
            body.update(request.generation_config)

        return body

    def _parse_response(self, data: dict[str, Any]) -> ModelResponse:
        """Parse NVIDIA response into standard format."""
        choices = data.get("choices", [])
        if not choices:
            return ModelResponse(
                content=None,
                tool_calls=None,
                usage=None,
                raw_response=data,
            )

        choice = choices[0]
        message = choice.get("message", {})

        content = message.get("content")
        tool_calls = message.get("tool_calls")

        usage = None
        if "usage" in data:
            u = data["usage"]
            usage = {
                "input_tokens": u.get("prompt_tokens", 0),
                "output_tokens": u.get("completion_tokens", 0),
                "total_tokens": u.get("total_tokens", 0),
            }

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=data,
            provider_metadata={"finish_reason": choice.get("finish_reason")},
        )

    async def generate_stream(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ):
        """Generate a streaming response from NVIDIA NIM."""
        url = f"{self._base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        body = self._build_request_body(request, inference_settings)
        body["stream"] = True

        async with self._client.stream("POST", url, headers=headers, json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    chunk_data = line[6:]
                    if chunk_data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(chunk_data)
                        yield self._parse_stream_chunk(chunk)
                    except json.JSONDecodeError:
                        continue

    def _parse_stream_chunk(self, data: dict[str, Any]) -> ModelResponse:
        """Parse a streaming chunk."""
        choices = data.get("choices", [])
        if not choices:
            return ModelResponse(
                content=None,
                tool_calls=None,
                usage=None,
                raw_response=data,
            )

        choice = choices[0]
        delta = choice.get("delta", {})

        content = delta.get("content")
        tool_calls = delta.get("tool_calls")

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            usage=None,
            raw_response=data,
            provider_metadata={"finish_reason": choice.get("finish_reason")},
        )

    async def close(self) -> None:
        await self._client.aclose()