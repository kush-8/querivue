"""Provider adapters for model gateway."""

from .base import ModelProvider, ModelRequest, ModelResponse
from .google import GoogleProvider
from .nvidia import NVIDIAProvider
from .openrouter import OpenRouterProvider
from .cloudflare import CloudflareProvider
from .ollama import OllamaProvider
from .ollama_cloud import OllamaCloudProvider

__all__ = [
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "GoogleProvider",
    "NVIDIAProvider",
    "OpenRouterProvider",
    "CloudflareProvider",
    "OllamaProvider",
    "OllamaCloudProvider",
]