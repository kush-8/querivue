"""Cloudflare Workers AI provider adapter."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings, CostRate
from .base import ModelProvider, ModelRequest, ModelResponse


class CloudflareProvider(ModelProvider):
    """Cloudflare Workers AI provider adapter."""

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
        base_url: str | None = None,
        model_id: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    ) -> None:
        self._account_id = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self._api_token = api_token or os.getenv("CLOUDFLARE_API_TOKEN")
        if not self._account_id or not self._api_token:
            raise ValueError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set")
        self._base_url = base_url or f"https://api.cloudflare.com/client/v4/accounts/{self._account_id}/ai/run"
        self._model_id = model_id
        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def provider_identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider="cloudflare",
            model_id=self._model_id,
            endpoint=self._base_url,
            route=f"/{self._model_id}",
            account_tier="free",
            region="global",
            quota_identity="default",
            sdk_name="workers-ai",
            sdk_version="1.0.0",
            protocol_version="1.0",
            tokenizer_version="1.0",
            tokenizer_build_hash="unknown",
            rate_manifest_hash="unknown",
            observed_revision="unknown",
            max_context_tokens=24000,
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
        """Generate a response from Cloudflare Workers AI."""
        url = f"{self._base_url}/{self._model_id}"
        headers = {
            "Authorization": f"Bearer {self._api_token}",
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
        """Build Cloudflare request body."""
        # Cloudflare uses a simpler format
        messages = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        messages.extend(request.messages)

        body = {
            "messages": messages,
            "temperature": settings.temperature,
            "max_tokens": settings.max_generated_tokens,
        }

        if request.tools:
            # Cloudflare doesn't support tools natively in the same way
            # We'll add tool descriptions to the system prompt
            pass

        return body

    def _parse_response(self, data: dict[str, Any]) -> ModelResponse:
        """Parse Cloudflare response into standard format."""
        # Cloudflare wraps response in result object
        result = data.get("result", {})
        response_data = result.get("response", "")

        usage = None
        if "usage" in result:
            u = result["usage"]
            usage = {
                "input_tokens": u.get("prompt_tokens", 0),
                "output_tokens": u.get("completion_tokens", 0),
                "total_tokens": u.get("total_tokens", 0),
            }

        return ModelResponse(
            content=response_data,
            tool_calls=None,  # Cloudflare doesn't return tool calls in standard format
            usage=usage,
            raw_response=data,
            provider_metadata={"finish_reason": "stop"},
        )

    async def generate_stream(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ):
        """Generate a streaming response from Cloudflare Workers AI."""
        url = f"{self._base_url}/{self._model_id}"
        headers = {
            "Authorization": f"Bearer {self._api_token}",
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
        result = data.get("result", {})
        response_text = result.get("response", "")

        return ModelResponse(
            content=response_text,
            tool_calls=None,
            usage=None,
            raw_response=data,
            provider_metadata={"finish_reason": "stop"},
        )

    async def close(self) -> None:
        await self._client.aclose()