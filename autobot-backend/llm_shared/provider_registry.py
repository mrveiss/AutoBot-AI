# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Provider registry for the multi-provider LLM layer (#1806).

The ProviderRegistry is the single source of truth for which providers are
available at runtime.  It supports:

  - Registration of BaseProvider instances by name
  - Ordered fallback chains (primary → secondary → … )
  - Per-conversation provider override (keyed by conversation_id)
  - Async health check with caching to avoid hammering providers
  - Lazy initialisation of the default provider set from autobot_shared.ssot_config

Usage:

    from llm_shared import get_provider_registry
from autobot_shared.logging_manager import get_logger

    registry = get_provider_registry()
    provider = await registry.get_provider_for_request(
        provider_name="openai",          # optional preference
        conversation_id="conv-abc123",   # optional per-conv override
    )
    response = await provider.chat_completion(request)
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from llm_shared.model_param_registry import apply_model_defaults, apply_prompt_prefix
from llm_shared.models import LLMRequest
from prepared_facts import ProviderRuntimeFact

from .base_provider import BaseProvider

logger = get_logger(__name__)

# Cache health results for 30 s to avoid a health check on every request.
_HEALTH_CACHE_TTL = 30.0

# Multiplier applied to baseline single-worker TTFT when evaluating whether
# cross-worker hop latency makes pipeline dispatch too expensive (MVA-1099).
_NPU_PIPELINE_MAX_LATENCY_MULTIPLIER: float = float(os.environ.get("NPU_PIPELINE_MAX_LATENCY_MULTIPLIER", "2.0"))

# Provider name used for the NPU worker pool.
_NPU_POOL_PROVIDER_NAME = "npu_pool"


class ProviderRegistry:
    """
    Manages the set of available LLM providers with fallback and per-conversation
    overrides.

    This is a per-process singleton (obtained via ``get_provider_registry()``).
    """

    def __init__(self) -> None:
        self._providers: Dict[str, BaseProvider] = {}
        self._fallback_chain: List[str] = []
        self._conversation_overrides: Dict[str, str] = {}
        # {provider_name: (is_available: bool, checked_at: float)}
        self._health_cache: Dict[str, tuple[bool, float]] = {}
        self._health_lock = asyncio.Lock()
        self._initialized = False
        self._provider_facts: Dict[str, ProviderRuntimeFact] = {}
        # Optional PipelineDispatcher wired in by set_npu_pipeline_dispatcher() (MVA-1099).
        self._npu_pipeline_dispatcher: Optional[Any] = None
        self._npu_pipeline_enabled: bool = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, provider: BaseProvider) -> None:
        """
        Register a provider instance.

        If a provider with the same name already exists it is replaced and a
        warning is emitted.
        """
        name = provider.provider_name
        if not name:
            raise ValueError("Provider must set provider_name before registration.")
        if name in self._providers:
            logger.warning("Replacing existing provider: %s", name)
        self._providers[name] = provider
        self._provider_facts[name] = ProviderRuntimeFact.build_at_startup(name, provider)
        logger.info("Registered provider: %s", name)

    def unregister(self, name: str) -> None:
        """Remove a provider from the registry."""
        if name in self._providers:
            del self._providers[name]
            self._health_cache.pop(name, None)
            self._provider_facts.pop(name, None)
            logger.info("Unregistered provider: %s", name)

    def set_fallback_chain(self, chain: List[str]) -> None:
        """
        Define the ordered list of provider names to try when no explicit
        provider is requested.  Local providers should appear before cloud
        providers to honour the local-first philosophy.
        """
        self._fallback_chain = list(chain)
        logger.info("Provider fallback chain: %s", chain)

    # ------------------------------------------------------------------
    # Per-conversation overrides
    # ------------------------------------------------------------------

    def set_conversation_provider(self, conversation_id: str, provider_name: str) -> None:
        """Pin a specific provider for a given conversation."""
        self._conversation_overrides[conversation_id] = provider_name
        logger.debug("Conversation %s pinned to provider %s", conversation_id, provider_name)

    def clear_conversation_provider(self, conversation_id: str) -> None:
        """Remove the per-conversation provider override."""
        self._conversation_overrides.pop(conversation_id, None)

    def get_conversation_provider_name(self, conversation_id: str) -> str | None:
        """Return the provider name pinned to this conversation, or None."""
        return self._conversation_overrides.get(conversation_id)

    async def _resolve_org_provider(self, org_id: str | None) -> str | None:
        """Return the org's persisted provider preference, or None (Issue #4451).

        Safe to call even when the knowledge Redis DB is unavailable — errors
        are swallowed and ``None`` is returned so the existing fallback chain
        still applies.
        """
        if org_id is None:
            return None
        try:
            from services.knowledge.org_knowledge_config import (
                get_org_knowledge_config_service,
            )

            cfg = await get_org_knowledge_config_service().get(org_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Per-org provider lookup failed for %s: %s", org_id, exc)
            return None
        return cfg.llm_provider if cfg else None

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def _check_health_cached(self, name: str) -> bool:
        """Check provider availability with a 30-second in-process cache."""
        now = time.monotonic()
        cached = self._health_cache.get(name)
        if cached and (now - cached[1]) < _HEALTH_CACHE_TTL:
            return cached[0]
        provider = self._providers.get(name)
        if provider is None:
            return False
        try:
            available = await provider.is_available()
        except Exception as exc:
            logger.warning("Health check for %s raised: %s", name, exc)
            available = False
        async with self._health_lock:
            self._health_cache[name] = (available, now)
        return available

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Run availability checks for every registered provider in parallel.

        Returns a dict of {provider_name: is_available}.
        """
        results = await asyncio.gather(
            *[self._check_health_cached(n) for n in self._providers],
            return_exceptions=False,
        )
        return dict(zip(self._providers.keys(), results))

    # ------------------------------------------------------------------
    # Model parameter injection (#3257)
    # ------------------------------------------------------------------

    @staticmethod
    def enrich_request(request: LLMRequest, provider_name: str) -> LLMRequest:
        """
        Merge per-model api_kwargs and prompt_prefix from the YAML registry into *request*.

        YAML defaults are applied first; caller-supplied
        ``request.metadata["api_kwargs"]`` always wins.  When a ``prompt_prefix``
        is configured for the model, it is prepended to the first user turn in
        ``request.messages`` (separated by a newline).  The request object is
        mutated in-place and also returned for convenience.

        Args:
            request:       The LLMRequest to enrich.
            provider_name: The provider that will handle the request.

        Returns:
            The same (mutated) request.
        """
        model = request.model_name or ""
        caller_kwargs: Dict[str, Any] = request.metadata.get("api_kwargs") or {}
        merged = apply_model_defaults(model, provider_name, caller_kwargs)
        request.metadata["api_kwargs"] = merged
        apply_prompt_prefix(model, request.messages)
        return request

    # ------------------------------------------------------------------
    # NPU pipeline dispatch (MVA-1099)
    # ------------------------------------------------------------------

    def set_npu_pipeline_dispatcher(self, dispatcher: Any, *, enabled: bool = True) -> None:
        """Attach a PipelineDispatcher and enable pipeline routing for oversized models."""
        self._npu_pipeline_dispatcher = dispatcher
        self._npu_pipeline_enabled = enabled
        logger.info("NPU pipeline dispatcher registered (enabled=%s)", enabled)

    async def _probe_hop_latency_ms(self) -> float:
        """Return estimated cross-worker hop latency in ms from the dispatcher's workers.

        Falls back to 0.0 when the dispatcher has fewer than two online workers.
        """
        if self._npu_pipeline_dispatcher is None:
            return 0.0
        from services.npu_pipeline.pipeline_dispatcher import WorkerState as WS

        online = [w for w in self._npu_pipeline_dispatcher.workers if w.state == WS.ONLINE]
        if len(online) < 2:
            return 0.0
        # Simulate a single cross-worker transfer to get the representative latency.
        try:
            latency = await self._npu_pipeline_dispatcher._simulate_layer_transfer(online[0], online[1])
        except Exception as exc:
            logger.debug("hop latency probe failed: %s", exc)
            return 0.0
        return latency

    async def _should_use_npu_pipeline(
        self,
        request: LLMRequest | None,
        baseline_ttft_ms: float = 500.0,
    ) -> bool:
        """Return True when pipeline dispatch is appropriate for *request*.

        Conditions (all must hold):
        - Pipeline is enabled via :meth:`set_npu_pipeline_dispatcher`
        - *request* carries a ``npu_model_bytes`` metadata key larger than the
          maximum single-worker VRAM in the registered dispatcher pool
        - Estimated cross-worker hop latency would not inflate TTFT beyond
          ``NPU_PIPELINE_MAX_LATENCY_MULTIPLIER × baseline_ttft_ms``
        """
        if not self._npu_pipeline_enabled or self._npu_pipeline_dispatcher is None:
            return False
        if request is None:
            return False

        model_bytes: int = request.metadata.get("npu_model_bytes", 0)
        if model_bytes <= 0:
            return False

        from services.npu_pipeline.pipeline_dispatcher import WorkerState as WS

        online = [w for w in self._npu_pipeline_dispatcher.workers if w.state == WS.ONLINE]
        if not online:
            return False

        max_single_vram = max(w.vram_bytes for w in online)
        if model_bytes <= max_single_vram:
            # Model fits on a single worker — no need for pipeline.
            return False

        # Latency guard: don't pipeline if hop cost exceeds the threshold.
        hop_ms = await self._probe_hop_latency_ms()
        # Each pipeline stage adds one hop; there are len(online)-1 hops total.
        total_hop_ms = hop_ms * max(0, len(online) - 1)
        threshold_ms = _NPU_PIPELINE_MAX_LATENCY_MULTIPLIER * baseline_ttft_ms
        if total_hop_ms > threshold_ms:
            logger.warning(
                "NPU pipeline hop latency %.1f ms exceeds threshold %.1f ms — "
                "falling back to single-worker dispatch",
                total_hop_ms,
                threshold_ms,
            )
            return False

        return True

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    async def get_provider(self, name: str) -> BaseProvider | None:
        """Return the named provider if registered and available, else None."""
        provider = self._providers.get(name)
        if provider is None:
            logger.debug("Provider not found: %s", name)
            return None
        if not await self._check_health_cached(name):
            logger.warning("Provider %s is unavailable", name)
            return None
        return provider

    async def get_provider_for_request(
        self,
        provider_name: str | None = None,
        conversation_id: str | None = None,
        request: LLMRequest | None = None,
        org_id: str | None = None,
    ) -> BaseProvider | None:
        """
        Return the best provider for a request, applying:

        1. Explicit ``provider_name`` argument (highest priority)
        2. Per-conversation override from ``conversation_id``
        3. Per-org persisted config via ``org_id`` (Issue #4451)
        4. Fallback chain order
        5. Any remaining registered provider

        When *request* is supplied, per-model api_kwargs from the YAML registry
        are merged into ``request.metadata["api_kwargs"]`` before returning
        (caller-supplied values always win).  See ``enrich_request()``.

        Returns None only if every registered provider is unreachable.
        """
        # Build candidate list in priority order
        candidates: List[str] = []
        if provider_name:
            candidates.append(provider_name)
        if conversation_id:
            conv_pref = self._conversation_overrides.get(conversation_id)
            if conv_pref and conv_pref not in candidates:
                candidates.append(conv_pref)
        # Issue #4451: per-org persisted provider preference.
        org_pref = await self._resolve_org_provider(org_id)
        if org_pref and org_pref not in candidates:
            candidates.append(org_pref)
        for name in self._fallback_chain:
            if name not in candidates:
                candidates.append(name)
        for name in self._providers:
            if name not in candidates:
                candidates.append(name)

        primary = candidates[0] if candidates else None
        for name in candidates:
            provider = await self.get_provider(name)
            if provider is not None:
                if request is not None:
                    self.enrich_request(request, name)
                if name != primary:
                    logger.debug(
                        "Fallback chain selected non-primary provider: %s (preferred: %s)",
                        name,
                        primary,
                    )
                # NPU pipeline hook (MVA-1099): when the chosen provider is the
                # NPU pool and the model is oversized for a single worker, route
                # through PipelineDispatcher instead.
                if name == _NPU_POOL_PROVIDER_NAME and await self._should_use_npu_pipeline(request):
                    logger.info(
                        "NPU pipeline dispatch activated for model_bytes=%s",
                        request.metadata.get("npu_model_bytes") if request else "n/a",
                    )
                    return self._npu_pipeline_dispatcher  # type: ignore[return-value]
                return provider

        logger.error("All providers unavailable or not configured")
        return None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_provider_by_name(self, name: str) -> BaseProvider | None:
        """Return the registered provider with the given name, or None (#5132).

        This is the public accessor for ``_providers``; callers should use this
        instead of accessing the private attribute directly.
        """
        return self._providers.get(name)

    def get_provider_facts(self) -> Dict[str, ProviderRuntimeFact]:
        """Return a snapshot of pre-computed provider capability facts (#7370)."""
        return dict(self._provider_facts)

    def list_providers(self) -> List[Dict[str, object]]:
        """Return a serialisable summary of registered providers."""
        return [
            {
                "name": name,
                "class": type(p).__name__,
            }
            for name, p in self._providers.items()
        ]

    def get_stats(self) -> Dict[str, object]:
        """Aggregate stats across all registered providers."""
        return {
            "providers": {n: p.get_stats() for n, p in self._providers.items()},
            "fallback_chain": list(self._fallback_chain),
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_registry_instance: ProviderRegistry | None = None
_registry_lock = asyncio.Lock()


def get_provider_registry() -> ProviderRegistry:
    """
    Return the process-level ProviderRegistry singleton.

    The first caller triggers lazy initialisation of default providers from the
    SSOT config.  Use ``initialize_default_providers()`` explicitly during
    application startup to control when this happens and to catch errors early.
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ProviderRegistry()
        _populate_default_providers(_registry_instance)
    return _registry_instance


def _populate_default_providers(registry: ProviderRegistry) -> None:
    """
    Register provider instances based on available configuration.

    Providers are registered only when they are enabled and (for cloud
    providers) when an API key is found.  Missing optional dependencies are
    handled gracefully so the application always starts.
    """

    from autobot_shared.ssot_config import get_config as get_ssot_config
    from llm_shared.providers.anthropic import AnthropicProvider
    from llm_shared.providers.custom_openai import CustomOpenAIProvider
    from llm_shared.providers.groq import GroqProvider
    from llm_shared.providers.huggingface import HuggingFaceProvider
    from llm_shared.providers.nous_portal import NousPortalProvider
    from llm_shared.providers.openai import OpenAIProvider
    from llm_shared.providers.openrouter import OpenRouterProvider
    from llm_shared.providers.vertexai import VertexAIProvider
    from llm_shared.providers.vllm_base import VLLMBaseProvider
    from llm_shared.providers.bedrock import BedrockProvider

    fallback: List[str] = []

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

    # OpenAI — registered when API key is present
    openai_key = config.openai_api_key
    if openai_key:
        openai_provider = OpenAIProvider(settings={"api_key": openai_key})
        registry.register(openai_provider)
        fallback.append(openai_provider.provider_name)
    else:
        logger.debug("OPENAI_API_KEY not set — OpenAI provider not registered")

    # Anthropic — registered when API key is present
    anthropic_key = config.anthropic_api_key
    if anthropic_key:
        anthropic_provider = AnthropicProvider(settings={"api_key": anthropic_key})
        registry.register(anthropic_provider)
        fallback.append(anthropic_provider.provider_name)
    else:
        logger.debug("ANTHROPIC_API_KEY not set — Anthropic provider not registered")

    # Groq — registered when API key is present
    groq_key = config.groq_api_key
    if groq_key:
        groq_provider = GroqProvider(settings={"api_key": groq_key})
        registry.register(groq_provider)
        fallback.append(groq_provider.provider_name)
    else:
        logger.debug("GROQ_API_KEY not set — Groq provider not registered")

    # HuggingFace — registered when HF token is present
    hf_token = config.hf_token or config.huggingface_api_token
    if hf_token:
        hf_provider = HuggingFaceProvider(settings={"api_token": hf_token})
        registry.register(hf_provider)
        fallback.append(hf_provider.provider_name)
    else:
        logger.debug("HF_TOKEN not set — HuggingFace provider not registered")

    # Custom OpenAI-compatible endpoint — registered when base URL is configured
    custom_url = config.custom_openai_base_url
    if custom_url:
        custom_provider = CustomOpenAIProvider(
            settings={
                "base_url": custom_url,
                "api_key": config.custom_openai_api_key,
                "default_model": config.custom_openai_default_model,
            }
        )
        registry.register(custom_provider)
        fallback.append(custom_provider.provider_name)
    else:
        logger.debug("CUSTOM_OPENAI_BASE_URL not set — custom OpenAI provider not registered")

    # OpenRouter — registered when API key is present (Issue #4341)
    openrouter_key = config.openrouter_api_key
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

    # Nous Portal — registered when API key is present (Issue #4341)
    nous_key = config.nous_api_key or config.hf_token or config.huggingface_api_token
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

    registry.set_fallback_chain(fallback)
    logger.info(
        "Provider registry initialised with %d providers: %s",
        len(fallback),
        fallback,
    )


__all__ = ["ProviderRegistry", "get_provider_registry"]
