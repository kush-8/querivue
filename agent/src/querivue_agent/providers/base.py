"""Base model provider interface and contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings, CostRate


@dataclass(frozen=True)
class ModelRequest:
    """Request to a model provider."""
    messages: list[dict[str, Any]]
    system_instruction: str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict[str, Any] | Literal["auto", "none"] | None = None
    generation_config: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ModelResponse:
    """Response from a model provider."""
    content: str | None
    tool_calls: list[dict[str, Any]] | None
    usage: dict[str, int] | None  # input_tokens, output_tokens, total_tokens
    raw_response: Any
    provider_metadata: dict[str, Any] | None = None


class ModelProvider(ABC):
    """Abstract base class for model providers."""

    @property
    @abstractmethod
    def provider_identity(self) -> ProviderIdentity:
        """Return the provider identity metadata."""
        pass

    @abstractmethod
    async def generate(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ) -> ModelResponse:
        """Generate a response from the model."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        request: ModelRequest,
        inference_settings: InferenceSettings,
    ) -> AsyncGenerator[ModelResponse, None]:
        """Generate a streaming response from the model."""
        pass

    def count_tokens(self, text: str) -> int:
        """Estimate token count (override for provider-specific counting)."""
        # Rough approximation: ~4 chars per token
        return len(text) // 4

    async def close(self) -> None:
        """Close any open connections."""
        pass


# Import AsyncGenerator
from typing import AsyncGenerator