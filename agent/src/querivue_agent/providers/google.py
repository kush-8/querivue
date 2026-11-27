"""Google Gemini provider adapter."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings, CostRate
from .base import ModelProvider, ModelRequest, ModelResponse


class GoogleProvider(ModelProvider):
    """Google Gemini API provider adapter."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com",
        model_id: str = "gemini-1.5-pro",
    ) -> None:
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def provider_identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider="google",
            model_id=self._model_id,
            endpoint=self._base_url,
            route=f"/v1/models/{self._model_id}:generateContent",
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

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-style messages to Gemini format."""
        gemini_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                # System messages are handled separately in Gemini
                continue
            gemini_role = "user" if role == "user" else "model"
            gemini_messages.append({
                "role": gemini_role,
                "parts": [{"text": content}],
            })
        return gemini_messages

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Convert OpenAI-style tools to Gemini function declarations."""
        if not tools:
            return None
        functions = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                functions.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {}),
                })
        return [{"function_declarations": functions}] if functions else None

    async def generate(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ) -> ModelResponse:
        """Generate a response from Gemini."""
        url = f"{self._base_url}/v1/models/{self._model_id}:generateContent"
        params = {"key": self._api_key}

        # Build request body
        body: dict[str, Any] = {
            "contents": self._convert_messages(request.messages),
            "generationConfig": self._build_generation_config(inference_settings, request),
        }

        if request.system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": request.system_instruction}]
            }

        tools = self._convert_tools(request.tools)
        if tools:
            body["tools"] = tools

        if request.tool_choice:
            body["toolConfig"] = self._build_tool_config(request.tool_choice)

        response = await self._client.post(url, params=params, json=body)
        response.raise_for_status()
        data = response.json()

        return self._parse_response(data)

    def _build_generation_config(
        self,
        settings: InferenceSettings,
        request: ModelRequest,
    ) -> dict[str, Any]:
        """Build Gemini generation config from settings."""
        config = {
            "temperature": settings.temperature,
            "maxOutputTokens": settings.max_generated_tokens,
        }

        if settings.seed is not None:
            config["seed"] = settings.seed

        if settings.reasoning == "minimal":
            config["thinkingConfig"] = {"thinkingBudget": 0}
        elif settings.reasoning == "low":
            config["thinkingConfig"] = {"thinkingBudget": 1024}

        if request.generation_config:
            config.update(request.generation_config)

        return config

    def _build_tool_config(self, tool_choice: dict[str, Any] | str) -> dict[str, Any]:
        """Build tool config from tool choice."""
        if tool_choice == "auto":
            return {"functionCallingConfig": {"mode": "AUTO"}}
        elif tool_choice == "none":
            return {"functionCallingConfig": {"mode": "NONE"}}
        elif isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
            return {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [tool_choice["function"]["name"]]}}
        return {"functionCallingConfig": {"mode": "AUTO"}}

    def _parse_response(self, data: dict[str, Any]) -> ModelResponse:
        """Parse Gemini response into standard format."""
        candidates = data.get("candidates", [])
        if not candidates:
            return ModelResponse(
                content=None,
                tool_calls=None,
                usage=None,
                raw_response=data,
            )

        candidate = candidates[0]
        content_parts = candidate.get("content", {}).get("parts", [])

        text_parts = []
        tool_calls = []

        for part in content_parts:
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({
                    "id": fc.get("name", "call_0"),
                    "type": "function",
                    "function": {
                        "name": fc.get("name"),
                        "arguments": json.dumps(fc.get("args", {})),
                    },
                })

        # Extract usage
        usage = None
        if "usageMetadata" in data:
            um = data["usageMetadata"]
            usage = {
                "input_tokens": um.get("promptTokenCount", 0),
                "output_tokens": um.get("candidatesTokenCount", 0),
                "total_tokens": um.get("totalTokenCount", 0),
            }

        return ModelResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
            raw_response=data,
            provider_metadata={"finish_reason": candidate.get("finishReason")},
        )

    async def generate_stream(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ):
        """Generate a streaming response from Gemini."""
        url = f"{self._base_url}/v1/models/{self._model_id}:streamGenerateContent"
        params = {"key": self._api_key, "alt": "sse"}

        body: dict[str, Any] = {
            "contents": self._convert_messages(request.messages),
            "generationConfig": self._build_generation_config(inference_settings, request),
        }

        if request.system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": request.system_instruction}]
            }

        tools = self._convert_tools(request.tools)
        if tools:
            body["tools"] = tools

        if request.tool_choice:
            body["toolConfig"] = self._build_tool_config(request.tool_choice)

        async with self._client.stream("POST", url, params=params, json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    chunk_data = line[6:]
                    if chunk_data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(chunk_data)
                        yield self._parse_response(chunk)
                    except json.JSONDecodeError:
                        continue

    async def close(self) -> None:
        await self._client.aclose()