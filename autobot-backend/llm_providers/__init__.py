# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Providers for AutoBot (#1806)

Supports multiple LLM backends for flexible model selection.

Provider implementations:
  BaseProvider          — abstract base class
  OllamaProvider        — local Ollama inference
  OpenAIProvider        — OpenAI GPT/o1 models
  AnthropicProvider     — Anthropic Claude models
  HuggingFaceProvider   — HuggingFace Inference API
  CustomOpenAIProvider  — any OpenAI-compatible endpoint
  VLLMProvider          — local vLLM inference server (existing)

Registry:
  ProviderRegistry      — manages providers, fallback chains, per-conv overrides
  get_provider_registry — process-level singleton accessor
"""

from .anthropic_provider import AnthropicProvider
from .base_provider import BaseProvider
from .custom_openai_provider import CustomOpenAIProvider
from .huggingface_provider import HuggingFaceProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider
from .provider_registry import ProviderRegistry, get_provider_registry
from .vllm_provider import RECOMMENDED_MODELS, VLLMModelManager, VLLMProvider

__all__ = [
    # Base
    "BaseProvider",
    # Providers
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "HuggingFaceProvider",
    "CustomOpenAIProvider",
    # vLLM (existing)
    "VLLMProvider",
    "VLLMModelManager",
    "RECOMMENDED_MODELS",
    # Registry
    "ProviderRegistry",
    "get_provider_registry",
]
