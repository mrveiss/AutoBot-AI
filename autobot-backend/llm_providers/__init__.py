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
  OpenRouterProvider    — OpenRouter multi-provider gateway (Issue #4341)
  NousPortalProvider    — Nous Research curated open-source models (Issue #4341)
  VLLMProvider          — local vLLM inference server (existing)

Registry:
  ProviderRegistry      — manages providers, fallback chains, per-conv overrides
  get_provider_registry — process-level singleton accessor
"""

# MVA-62 Consolidation: core infrastructure now in llm_interface_pkg
# This module is maintained as a backward-compat re-export shim
from llm_interface_pkg import BaseProvider, ProviderRegistry, get_provider_registry

# Provider implementations remain here (Phase 3 consolidation will move these)
from .anthropic_provider import AnthropicProvider
from .custom_openai_provider import CustomOpenAIProvider
from .groq_provider import GroqProvider
from .huggingface_provider import HuggingFaceProvider
from .nous_portal_provider import NousPortalProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider
from .openrouter_provider import OpenRouterProvider
from .vllm_provider import RECOMMENDED_MODELS, VLLMModelManager, VLLMProvider

__all__ = [
    # Base
    "BaseProvider",
    # Providers
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GroqProvider",
    "HuggingFaceProvider",
    "CustomOpenAIProvider",
    "OpenRouterProvider",
    "NousPortalProvider",
    # vLLM (existing)
    "VLLMProvider",
    "VLLMModelManager",
    "RECOMMENDED_MODELS",
    # Registry
    "ProviderRegistry",
    "get_provider_registry",
]
