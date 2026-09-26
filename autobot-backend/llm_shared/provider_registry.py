# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import time
from typing import Any, Dict, List, Optional

from autobot_shared.credential_gated_registry import (
    CredentialGatedRegistry,
    gated_registry_singleton,
)
from autobot_shared.env_utils import env_float
from autobot_shared.llm_provider_candidates import (
    build_candidate_selection,
    describe_exclusions,
    describe_exhaustion,
)
from autobot_shared.logging_manager import get_logger
from llm_shared.model_param_registry import apply_model_defaults, apply_prompt_prefix
from llm_shared.models import LLMRequest
from prepared_facts import ProviderRuntimeFact

from .base_provider import BaseProvider
from .provider_degradation import get_degradation_store

logger = get_logger(__name__)

# Per-run credential primitives live in the lightweight run_credentials module
# (GH#9037); re-exported here for backward compatibility.
from .run_credentials import (  # noqa: E402,F401
    RunCredentialContext,
    get_run_credentials,
    set_run_credentials,
)

# Cache health results for 30 s to avoid a health check on every request.
_HEALTH_CACHE_TTL = 30.0

# Multiplier applied to baseline single-worker TTFT when evaluating whether
# cross-worker hop latency makes pipeline dispatch too expensive (MVA-1099).
_NPU_PIPELINE_MAX_LATENCY_MULTIPLIER: float = env_float("NPU_PIPELINE_MAX_LATENCY_MULTIPLIER", 2.0)

# Provider name used for the NPU worker pool.
_NPU_POOL_PROVIDER_NAME = "npu_pool"


class ProviderRegistry(CredentialGatedRegistry[BaseProvider]):
    """
    Manages the set of available LLM providers with fallback and per-conversation
    overrides.

    Built on ``CredentialGatedRegistry`` (#11664) — shared with the search and
    capability registries. This is a per-process singleton (obtained via
    ``get_provider_registry()``).
    """

    def __init__(self) -> None:
        super().__init__()  # sets self._providers (#11664)
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
        self._store_entry(name, provider)
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
        # #11498: is_available() is a cheap ping that can pass while completions
        # consistently fail. If this provider's completion breaker is OPEN and
        # still cooling, treat it as unavailable so selection routes to the
        # fallback chain instead of repeatedly picking a fail-fasting provider.
        if available and self._completion_breaker_is_rejecting(name):
            available = False
        async with self._health_lock:
            self._health_cache[name] = (available, now)
        return available

    @staticmethod
    def _completion_breaker_is_rejecting(name: str) -> bool:
        """True when *name*'s ``{name}_service`` completion breaker is OPEN and
        cooling (#11498). Read-only lookup — never creates a breaker."""
        from circuit_breaker import get_circuit_breaker_manager

        breaker = get_circuit_breaker_manager().circuit_breakers.get(f"{name}_service")
        return breaker is not None and breaker.is_rejecting

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

    def _create_ephemeral_provider(
        self,
        provider_name: str,
        runtime_credentials: Dict[str, Any],
    ) -> BaseProvider | None:
        """Create a temporary provider instance with runtime credentials (GH#9037).

        Args:
            provider_name: Name of the provider to instantiate.
            runtime_credentials: Settings dict with API keys, base URLs, etc.

        Returns:
            Ephemeral provider instance, or None if the provider type is unknown.
        """
        from llm_shared.providers.anthropic import AnthropicProvider
        from llm_shared.providers.bedrock import BedrockProvider
        from llm_shared.providers.custom_openai import CustomOpenAIProvider
        from llm_shared.providers.groq import GroqProvider
        from llm_shared.providers.huggingface import HuggingFaceProvider
        from llm_shared.providers.mistral import MistralProvider
        from llm_shared.providers.nous_portal import NousPortalProvider
        from llm_shared.providers.ollama_provider import OllamaProvider
        from llm_shared.providers.openai import OpenAIProvider
        from llm_shared.providers.openrouter import OpenRouterProvider
        from llm_shared.providers.vertexai import VertexAIProvider
        from llm_shared.providers.vllm_base import VLLMBaseProvider

        provider_map = {
            "anthropic": AnthropicProvider,
            "openai": OpenAIProvider,
            "ollama": OllamaProvider,
            "groq": GroqProvider,
            "mistral": MistralProvider,
            "huggingface": HuggingFaceProvider,
            "custom_openai": CustomOpenAIProvider,
            "openrouter": OpenRouterProvider,
            "nous_portal": NousPortalProvider,
            "vllm": VLLMBaseProvider,
            "vertexai": VertexAIProvider,
            "bedrock": BedrockProvider,
        }

        provider_class = provider_map.get(provider_name)
        if provider_class is None:
            logger.warning("Unknown provider for ephemeral instantiation: %s", provider_name)
            return None

        try:
            # Instantiate provider with runtime credentials
            provider = provider_class(settings=runtime_credentials)
            logger.info(
                "Created ephemeral provider: %s (credentials from run context)",
                provider_name,
            )
            return provider
        except Exception as exc:
            logger.error("Failed to create ephemeral provider %s: %s", provider_name, exc)
            return None

    async def get_provider(self, name: str) -> BaseProvider | None:
        """Return the named provider if registered and available, else None."""
        # Check for runtime credential override (GH#9037)
        run_ctx = get_run_credentials()
        if run_ctx:
            runtime_creds = run_ctx.get_credentials(name)
            if runtime_creds:
                # Create ephemeral provider with runtime credentials
                ephemeral = self._create_ephemeral_provider(name, runtime_creds)
                if ephemeral:
                    logger.debug(
                        "Using ephemeral provider %s with runtime credentials",
                        name,
                    )
                    return ephemeral
                # Fall through to registered provider if ephemeral creation fails

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

        Returns None when every permitted provider is unreachable, or when the
        configured order permits none of the registered providers -- two different
        failures, distinguished in the log line rather than in the return value.
        """
        # Build candidate list in priority order (rules in autobot_shared/llm_provider_candidates.py).
        selection = build_candidate_selection(
            explicit=provider_name,
            conversation_preference=(self._conversation_overrides.get(conversation_id) if conversation_id else None),
            org_preference=await self._resolve_org_provider(org_id),  # Issue #4451
            chain=self._fallback_chain,
            registered=self._providers,
        )
        candidates: List[str] = list(selection.candidates)
        held_out = describe_exclusions(selection)
        if held_out:
            logger.debug("%s", held_out)

        primary = candidates[0] if candidates else None
        model_name: str | None = request.model_name if request else None
        degradation = get_degradation_store()

        # Determine which candidates are currently degraded (Issue #11519).
        # All candidates are checked up-front so we can detect the all-degraded
        # edge case and fall through rather than returning None.
        degraded_set: set[str] = set()
        for name in candidates:
            if await degradation.is_degraded(name, model_name):
                degraded_set.add(name)
        all_degraded = len(candidates) > 0 and degraded_set == set(candidates)
        if all_degraded:
            logger.warning(
                "degradation: all %d candidates degraded — proceeding anyway",
                len(candidates),
            )

        degraded_skipped: list[str] = []
        for name in candidates:
            if name in degraded_set and not all_degraded:
                logger.debug("degradation: skipping degraded provider %s", name)
                degraded_skipped.append(name)
                continue
            provider = await self.get_provider(name)
            if provider is not None:
                if request is not None:
                    self.enrich_request(request, name)
                    # Record the resolved provider so the fallback coordinator
                    # marks the provider actually used, not the (possibly
                    # absent) one on the request (#11519).
                    request.metadata["selected_provider"] = name
                    # Attach observability field so callers know what was skipped.
                    if degraded_skipped:
                        request.metadata["degraded_skipped"] = degraded_skipped
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

        logger.error("%s", describe_exhaustion(selection))
        return None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_provider_by_name(self, name: str) -> BaseProvider | None:
        """Return the registered provider with the given name, or None (#5132).

        This is the public accessor for ``_providers``; callers should use this
        instead of accessing the private attribute directly.
        """
        return self._get_entry(name)

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


def _populate_default_providers(registry: ProviderRegistry) -> None:
    """
    Register provider instances based on available configuration.

    Providers are registered only when they are enabled and (for cloud
    providers) when an API key is found.  Missing optional dependencies are
    handled gracefully so the application always starts.

    The chain the registry stores is ``AUTOBOT_LLM_PROVIDER_ORDER`` applied to
    the registration order, not the registration order itself (#15500): the
    order a provider is built in must not decide which one serves a request.

    The registrations themselves live in ``llm_shared.providers.bootstrap``,
    which also records why that module sits under ``providers/`` and why its
    import placements are the way they are. Imported here at call time, as
    every provider import in this function always was, so a provider module
    that cannot import fails the population rather than the module load.
    """
    from autobot_shared.llm_provider_order import apply_configured_order
    from llm_shared.providers.bootstrap import register_default_providers

    registry.set_fallback_chain(apply_configured_order(register_default_providers(registry)))


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

# Process-level ProviderRegistry singleton: the first caller triggers lazy
# initialisation of default providers from the SSOT config. Population
# failures are logged, never raised (see gated_registry_singleton, #11664).
get_provider_registry = gated_registry_singleton(
    ProviderRegistry,
    _populate_default_providers,
    log=logger,
)


__all__ = [
    "ProviderRegistry",
    "get_provider_registry",
    "RunCredentialContext",
    "set_run_credentials",
    "get_run_credentials",
]
