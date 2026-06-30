# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Provider implementations for the multi-provider LLM layer.

Phase 2 consolidation (MVA-178 / GH#7637): all provider implementations
have been moved from ``llm_providers/`` into this package.

Cloud API providers:
    AnthropicProvider      — Anthropic Claude (with OTel tracing restored, #697)
    BedrockProvider        — AWS Bedrock (Claude, Llama, Mistral, Titan, Nova, GH#9010)
    OpenAIProvider         — OpenAI GPT/o1 (OTel tracing, circuit breaker)
    GroqProvider           — Groq ultra-low-latency inference
    MistralProvider        — Mistral Le Chat / Codestral / Devstral (#10549)
    HuggingFaceProvider    — HuggingFace Inference API
    CustomOpenAIProvider   — Any OpenAI-compatible endpoint
    OpenRouterProvider     — OpenRouter multi-provider gateway (#4341)
    NousPortalProvider     — Nous Research curated open-source models (#4341)
    VertexAIProvider       — Google Cloud Vertex AI (Gemini + Claude on Vertex, GH#9009)

Local/self-hosted providers:
    OllamaProvider         — Registry-facing Ollama (delegates to inner ollama.py)
    VLLMBaseProvider       — vLLM wrapped in BaseProvider interface
    VLLMProvider           — Raw vLLM inference engine
    VLLMModelManager       — Multi-model vLLM manager
    TransformersProvider   — HuggingFace Transformers

Utilities:
    render_chat_template   — Jinja2 chat template renderer (chatml/zephyr/vicuna)
    DEFAULT_TEMPLATE       — Default template name ("chatml")

Legacy shared infra (retained from #3185):
    MockHandler / LocalHandler — test/mock providers
"""

# Cloud API providers (Phase 2 — moved from llm_providers/)
from .anthropic import AnthropicProvider
from .bedrock import BEDROCK_MODELS, BedrockProvider

# Utilities
from .chat_template_loader import DEFAULT_TEMPLATE, render_chat_template
from .custom_openai import CustomOpenAIProvider
from .groq import GROQ_MODELS, GroqProvider
from .huggingface import HuggingFaceProvider
from .mistral import MISTRAL_MODELS, MistralProvider

# Local/self-hosted providers
from .mock_handler import LocalHandler, MockHandler
from .nous_portal import NOUS_MODELS, NousPortalProvider
from .ollama_provider import OllamaProvider  # registry-facing
from .openai import OpenAIProvider
from .openrouter import OpenRouterProvider
from .transformers_provider import TransformersProvider
from .vertexai import VERTEX_MODELS, VertexAIProvider
from .vllm import RECOMMENDED_MODELS, VLLMModelManager, VLLMProvider
from .vllm_base import VLLMBaseProvider

__all__ = [
    # Cloud API providers
    "AnthropicProvider",
    "BedrockProvider",
    "BEDROCK_MODELS",
    "OpenAIProvider",
    "GroqProvider",
    "GROQ_MODELS",
    "MistralProvider",
    "MISTRAL_MODELS",
    "HuggingFaceProvider",
    "CustomOpenAIProvider",
    "OpenRouterProvider",
    "NousPortalProvider",
    "NOUS_MODELS",
    "VertexAIProvider",
    "VERTEX_MODELS",
    # Local/self-hosted
    "OllamaProvider",
    "VLLMBaseProvider",
    "VLLMProvider",
    "VLLMModelManager",
    "RECOMMENDED_MODELS",
    "TransformersProvider",
    "MockHandler",
    "LocalHandler",
    # Utilities
    "render_chat_template",
    "DEFAULT_TEMPLATE",
]
