# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Build the default provider set from configuration (#15500).

Extracted from ``provider_registry._populate_default_providers``, which had
grown to 175 body lines and tripped the #620 function-length gate the moment
#15500 touched it.  ``provider_registry.py`` sits on its grandfathered size
ceiling, so the helpers could not be added there -- and splitting is the
answer the ceiling asks for anyway.

Why this module lives under ``providers/`` rather than beside the registry:
the backend's conftest stubs the ``llm_shared`` package without a real
``__path__`` and real-loads named submodules one line at a time, in a file
that is *also* on its ceiling.  ``llm_shared.providers`` is given the real
directory (#11796), so a module here is importable from disk with no conftest
entry at all.

Two import placements are deliberate and load-bearing:

* The provider classes are imported at MODULE level.  In the original one
  function they were all imported together at its top, so a provider module
  that failed to import stopped the whole population -- caught and logged by
  ``gated_registry_singleton``, never raised.  Module level preserves that
  all-or-nothing behaviour; per-helper imports would quietly turn it into
  "the groups before the broken one still register".
* ``resolve_provider_key`` is imported INSIDE each helper that uses it,
  exactly as before.  ``llm_shared/tests/test_provider_registry_key_coverage.py``
  patches the attribute on ``services.provider_key_vault`` and then runs the
  build, so the name has to be looked up after the patch.  A module-level
  ``from ... import resolve_provider_key`` here would bind the real function
  at import time and that suite would record nothing while still passing.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from autobot_shared.ssot_config import get_config as get_ssot_config
from llm_shared.providers.anthropic import AnthropicProvider
from llm_shared.providers.bedrock import BedrockProvider
from llm_shared.providers.custom_openai import CustomOpenAIProvider
from llm_shared.providers.groq import GroqProvider
from llm_shared.providers.huggingface import HuggingFaceProvider
from llm_shared.providers.mistral import MistralProvider
from llm_shared.providers.nous_portal import NousPortalProvider
from llm_shared.providers.openai import OpenAIProvider
from llm_shared.providers.openrouter import OpenRouterProvider
from llm_shared.providers.vertexai import VertexAIProvider
from llm_shared.providers.vllm_base import VLLMBaseProvider

if TYPE_CHECKING:
    from llm_shared.provider_registry import ProviderRegistry

logger = get_logger(__name__)


def _register_local(registry: "ProviderRegistry", fallback: List[str]) -> None:
    """Ollama, which needs no credential and so always registers."""
    # Ollama (local) — always registered, highest priority
    try:
        ssot = get_ssot_config()
        ollama_url = ssot.ollama_url if ssot else config.ollama_endpoint
        from llm_shared.providers.ollama_provider import OllamaProvider

        ollama_provider = OllamaProvider(settings={"base_url": ollama_url})
        registry.register(ollama_provider)
        fallback.append(ollama_provider.provider_name)
    except Exception as exc:
        logger.debug("Ollama provider not registered: %s", exc)


def _register_api_key_providers(registry: "ProviderRegistry", fallback: List[str]) -> str:
    """The providers gated on nothing but an API key.

    Returns the HuggingFace token, which the Nous Portal registration reuses as
    its own fallback credential (#15268).
    """
    from services.provider_key_vault import resolve_provider_key

    # OpenAI — registered when API key is present (env wins; else System vault, #10088 Task 7)
    openai_key = resolve_provider_key("OPENAI_API_KEY", config.openai_api_key)
    if openai_key:
        openai_provider = OpenAIProvider(settings={"api_key": openai_key})
        registry.register(openai_provider)
        fallback.append(openai_provider.provider_name)
    else:
        logger.debug("OPENAI_API_KEY not set — OpenAI provider not registered")

    # Anthropic — registered when API key is present (env wins; else System vault, #10088 Task 7)
    anthropic_key = resolve_provider_key("ANTHROPIC_API_KEY", config.anthropic_api_key)
    if anthropic_key:
        anthropic_provider = AnthropicProvider(settings={"api_key": anthropic_key})
        registry.register(anthropic_provider)
        fallback.append(anthropic_provider.provider_name)
    else:
        logger.debug("ANTHROPIC_API_KEY not set — Anthropic provider not registered")

    # Groq — registered when API key is present (env wins; else System vault, #10088 Task 7)
    groq_key = resolve_provider_key("GROQ_API_KEY", config.groq_api_key)
    if groq_key:
        groq_provider = GroqProvider(settings={"api_key": groq_key})
        registry.register(groq_provider)
        fallback.append(groq_provider.provider_name)
    else:
        logger.debug("GROQ_API_KEY not set — Groq provider not registered")

    # Mistral — registered when API key is present (Issue #10549; env wins else vault, #10088 Task 7)
    mistral_key = resolve_provider_key("MISTRAL_API_KEY", config.mistral_api_key)
    if mistral_key:
        mistral_provider = MistralProvider(
            settings={
                "api_key": mistral_key,
                "base_url": config.mistral_api_base_url or None,
                "default_model": config.mistral_default_model or None,
            }
        )
        registry.register(mistral_provider)
        fallback.append(mistral_provider.provider_name)
    else:
        logger.debug("MISTRAL_API_KEY not set — Mistral provider not registered")

    # HuggingFace — HF token, reused below as the Nous Portal fallback (env wins; else vault, #15268).
    hf_token = resolve_provider_key("HF_TOKEN", config.hf_token) or resolve_provider_key(
        "HUGGINGFACE_API_TOKEN", config.huggingface_api_token
    )
    if hf_token:
        hf_provider = HuggingFaceProvider(settings={"api_token": hf_token})
        registry.register(hf_provider)
        fallback.append(hf_provider.provider_name)
    else:
        logger.debug("HF_TOKEN not set — HuggingFace provider not registered")
    return hf_token


def _register_openai_compatible(registry: "ProviderRegistry", fallback: List[str]) -> None:
    """Endpoints speaking the OpenAI dialect, gated on a URL or a key."""
    from services.provider_key_vault import resolve_provider_key

    # Custom OpenAI-compatible endpoint — registered when base URL is configured
    custom_url = config.custom_openai_base_url
    if custom_url:
        custom_provider = CustomOpenAIProvider(
            settings={
                "base_url": custom_url,
                # env wins; else System vault (#10088 Task 7)
                "api_key": resolve_provider_key("CUSTOM_OPENAI_API_KEY", config.custom_openai_api_key),
                "default_model": config.custom_openai_default_model,
            }
        )
        registry.register(custom_provider)
        fallback.append(custom_provider.provider_name)
    else:
        logger.debug("CUSTOM_OPENAI_BASE_URL not set — custom OpenAI provider not registered")

    # OpenRouter — registered when API key is present (Issue #4341; env wins else vault, #10088 Task 7)
    openrouter_key = resolve_provider_key("OPENROUTER_API_KEY", config.openrouter_api_key)
    if openrouter_key:
        try:
            openrouter_provider = OpenRouterProvider(
                settings={
                    "api_key": openrouter_key,
                    "default_model": config.openrouter_default_model,
                }
            )
            registry.register(openrouter_provider)
            fallback.append(openrouter_provider.provider_name)
        except Exception as exc:
            logger.debug("OpenRouter provider not registered: %s", exc)
    else:
        logger.debug("OPENROUTER_API_KEY not set — OpenRouter provider not registered")


def _register_hosted_inference(registry: "ProviderRegistry", fallback: List[str], hf_token: str) -> None:
    """Nous Portal and vLLM: a curated gateway and a self-hosted engine."""
    from services.provider_key_vault import resolve_provider_key

    # Nous Portal — registered when API key is present (Issue #4341; env wins else vault, #10088 Task 7).
    nous_key = resolve_provider_key("NOUS_API_KEY", config.nous_api_key) or hf_token
    if nous_key:
        try:
            nous_provider = NousPortalProvider(
                settings={
                    "api_key": nous_key,
                    "default_model": config.misc.nous_default_model or "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
                }
            )
            registry.register(nous_provider)
            fallback.append(nous_provider.provider_name)
        except Exception as exc:
            logger.debug("Nous Portal provider not registered: %s", exc)
    else:
        logger.debug("NOUS_API_KEY not set — Nous Portal provider not registered")

    # vLLM — registered when model configuration is provided (Issue #4341)
    vllm_model = config.vllm_model
    if vllm_model:
        try:
            vllm_provider = VLLMBaseProvider(
                settings={
                    "model": vllm_model,
                    "tensor_parallel_size": int(config.vllm_tensor_parallel_size),
                    "gpu_memory_utilization": float(config.vllm_gpu_memory_utilization),
                    "dtype": config.vllm_dtype,
                }
            )
            registry.register(vllm_provider)
            fallback.append(vllm_provider.provider_name)
        except Exception as exc:
            logger.debug("vLLM provider not registered: %s", exc)
    else:
        logger.debug("VLLM_MODEL not set — vLLM provider not registered")


def _register_cloud_providers(registry: "ProviderRegistry", fallback: List[str]) -> None:
    """The two providers authenticated by cloud project or role rather than key."""
    # Vertex AI — registered when GCP project is configured (GH#9009)
    vertex_project = config.vertex_ai_project
    if vertex_project:
        try:
            vertex_provider = VertexAIProvider(
                settings={
                    "project": vertex_project,
                    "location": config.vertex_ai_location,
                    "service_account_json": config.vertex_ai_service_account_json,
                    "default_model": config.vertex_ai_default_model,
                }
            )
            registry.register(vertex_provider)
            fallback.append(vertex_provider.provider_name)
        except Exception as exc:
            logger.debug("Vertex AI provider not registered: %s", exc)
    else:
        logger.debug("VERTEX_AI_PROJECT not set — Vertex AI provider not registered")

    # AWS Bedrock — registered when AWS credentials are available (GH#9010)
    # Credentials can come from env vars (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)
    # or IAM role (automatic in EC2/ECS). Region defaults to us-east-1.
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    # Register if credentials are explicitly provided OR if we're in an AWS environment
    # (IAM role will be used automatically by boto3)
    if aws_access_key and aws_secret_key:
        try:
            bedrock_provider = BedrockProvider(
                settings={
                    "aws_access_key_id": aws_access_key,
                    "aws_secret_access_key": aws_secret_key,
                    "region": aws_region,
                    "default_model": "claude-3-5-sonnet",
                }
            )
            registry.register(bedrock_provider)
            fallback.append(bedrock_provider.provider_name)
        except Exception as exc:
            logger.debug("Bedrock provider not registered: %s", exc)
    else:
        # Try IAM role registration (will work in EC2/ECS without explicit credentials)
        try:
            bedrock_provider = BedrockProvider(
                settings={
                    "region": aws_region,
                    "default_model": "claude-3-5-sonnet",
                }
            )
            registry.register(bedrock_provider)
            fallback.append(bedrock_provider.provider_name)
            logger.debug("Bedrock provider registered with IAM role authentication")
        except Exception as exc:
            logger.debug("Bedrock provider not registered (no credentials or IAM role): %s", exc)


def register_default_providers(registry: "ProviderRegistry") -> List[str]:
    """Register every configured provider and return them in registration order.

    The returned order is NOT the fallback chain: the caller hands it to
    ``apply_configured_order`` so the chain is configuration rather than the
    sequence of calls below (#15500).
    """
    fallback: List[str] = []

    _register_local(registry, fallback)
    hf_token = _register_api_key_providers(registry, fallback)
    _register_openai_compatible(registry, fallback)
    _register_hosted_inference(registry, fallback, hf_token)
    _register_cloud_providers(registry, fallback)

    return fallback


__all__ = ["register_default_providers"]
