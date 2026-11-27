"""Ollama provider adapter."""

from __future__ import annotations

import json
import os
from typing import Any, AsyncGenerator

import httpx

from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings, CostRate
from .base import ModelProvider, ModelRequest, ModelResponse


class OllamaProvider(ModelProvider):
    """Ollama local model provider adapter."""

    def __init__(
        self,
        base_url: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self._base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._model_id = model_id or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def provider_identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider="ollama",
            model_id=self._model_id,
            endpoint=self._base_url,
            route=f"/api/generate",
            account_tier="local",
            region="local",
            quota_identity="unlimited",
            sdk_name="ollama-python",
            sdk_version="0.1.0",
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
        """Generate a response from Ollama."""
        url = f"{self._base_url}/api/generate"

        # Build prompt combining system and messages
        prompt_parts = []
        if request.system_instruction:
            prompt_parts.append(f"System: {request.system_instruction}")
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prompt_parts.append(f"{role.capitalize()}: {content}")
        prompt = "\n\n".join(prompt_parts)

        body = {
            "model": self._model_id,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": inference_settings.temperature,
                "num_predict": inference_settings.max_generated_tokens,
            },
        }

        response = await self._client.post(url, json=body)
        response.raise_for_status()
        data = response.json()

        return self._parse_response(data)

    def _parse_response(self, data: dict[str, Any]) -> ModelResponse:
        """Parse Ollama response into standard format."""
        content = data.get("response", "")

        usage = None
        if "prompt_eval_count" in data or "eval_count" in data:
            usage = {
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            }

        return ModelResponse(
            content=content,
            tool_calls=None,  # Ollama doesn't return tool calls in standard format
            usage=usage,
            raw_response=data,
            provider_metadata={"finish_reason": data.get("done_reason", "stop")},
        )

    async def generate_stream(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ) -> AsyncGenerator[ModelResponse, None]:
        """Generate a streaming response from Ollama."""
        url = f"{self._base_url}/api/generate"

        prompt_parts = []
        if request.system_instruction:
            prompt_parts.append(f"System: {request.system_instruction}")
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prompt_parts.append(f"{role.capitalize()}: {content}")
        prompt = "\n\n".join(prompt_parts)

        body = {
            "model": self._model_id,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": inference_settings.temperature,
                "num_predict": inference_settings.max_generated_tokens,
            },
        }

        async with self._client.stream("POST", url, json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    yield self._parse_stream_chunk(chunk)
                    if chunk.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue

    def _parse_stream_chunk(self, data: dict[str, Any]) -> ModelResponse:
        """Parse a streaming chunk."""
        content = data.get("response", "")

        return ModelResponse(
            content=content,
            tool_calls=None,
            usage=None,
            raw_response=data,
            provider_metadata={"finish_reason": data.get("done_reason", "stop")},
        )

    async def close(self) -> None:
        await self._client.aclose()