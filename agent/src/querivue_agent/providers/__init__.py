"""Provider adapters for model gateway."""

from .base import ModelProvider, ModelRequest, ModelResponse
from .openrouter import OpenRouterProvider
from .ollama_cloud import OllamaCloudProvider

__all__ = [
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "OpenRouterProvider",
    "OllamaCloudProvider",
]