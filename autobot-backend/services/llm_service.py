# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unified LLM service for the multi-provider LLM layer (#1806).

LLMService is the single entry-point for all inference in AutoBot.  It:

  - Resolves the correct provider for each request via the ProviderRegistry
  - Supports per-conversation model/provider selection
  - Enforces per-task-type defaults (temperature, max_tokens)
  - Provides both blocking and streaming interfaces
  - Forwards cost/usage data to the LLMCostTracker when available

Usage example::

    from services.llm_service import get_llm_service
from autobot_shared.logging_manager import get_logger

    svc = get_llm_service()
    response = await svc.chat(
        messages=[{"role": "user", "content": "Hello"}],
        conversation_id="conv-abc123",
        provider_name="openai",         # optional
        model_name="gpt-4o-mini",       # optional
    )
    print(response.content)

    async for chunk in svc.stream(
        messages=[{"role": "user", "content": "Explain async/await"}],
        conversation_id="conv-abc123",
    ):
        print(chunk, end="", flush=True)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config
from autobot_shared.tracing import get_tracer
from llm_shared import ProviderRegistry, get_provider_registry
from llm_shared.cache import CachedResponse, get_llm_cache
from llm_shared.fallback_chain import get_fallback_chain_manager
from llm_shared.models import LLMRequest, LLMResponse
from llm_shared.rate_limit_backoff import extract_rate_limit_info
from llm_shared.tiered_routing import TierConfig, TieredModelRouter
from llm_shared.types import LLMType

try:
    from services.provider_health import ProviderHealthManager, ProviderStatus

    _HEALTH_CHECK_AVAILABLE = True
except Exception:  # pragma: no cover
    _HEALTH_CHECK_AVAILABLE = False
    ProviderHealthManager = None  # type: ignore[assignment]
    ProviderStatus = None  # type: ignore[assignment]

# OTel tracer shared with llm_shared — same span names so traces merge.
_llm_tracer = get_tracer("autobot.llm")

logger = get_logger(__name__)

# Cap on honoring a provider-suggested Retry-After before a same-provider retry,
# so a hostile/huge value can't stall the request indefinitely (#10601).
_MAX_RETRY_AFTER_SECONDS = float(os.getenv("AUTOBOT_LLM_MAX_RETRY_AFTER_SECONDS", "30"))

# Default parameters per task type.  These are applied when the caller does
# not supply explicit temperature / max_tokens values.
_TASK_TYPE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    LLMType.CHAT.value: {"temperature": 0.7, "max_tokens": 2048},
    LLMType.RAG.value: {"temperature": 0.2, "max_tokens": 1024},
    LLMType.EXTRACTION.value: {"temperature": 0.1, "max_tokens": 1024},
    LLMType.CLASSIFICATION.value: {"temperature": 0.1, "max_tokens": 256},
    LLMType.ORCHESTRATOR.value: {"temperature": 0.3, "max_tokens": 2048},
    LLMType.TASK.value: {"temperature": 0.5, "max_tokens": 1024},
    LLMType.ANALYSIS.value: {"temperature": 0.4, "max_tokens": 2048},
    LLMType.GENERAL.value: {"temperature": 0.7, "max_tokens": 1024},
}


def _normalize_llm_type(llm_type: str | LLMType | None) -> LLMType:
    """Coerce string or None to an LLMType enum value."""
    if isinstance(llm_type, LLMType):
        return llm_type
    if isinstance(llm_type, str):
        try:
            return LLMType(llm_type.lower())
        except ValueError:
            pass
    return LLMType.GENERAL


def _apply_task_defaults(
    llm_type: LLMType,
    temperature: float | None,
    max_tokens: int | None,
) -> tuple[float, int | None]:
    """
    Return (temperature, max_tokens) with task-type defaults filled in.

    Explicit caller values always take priority.
    """
    defaults = _TASK_TYPE_DEFAULTS.get(llm_type.value, _TASK_TYPE_DEFAULTS["general"])
    resolved_temp = temperature if temperature is not None else defaults["temperature"]
    resolved_tokens = max_tokens if max_tokens is not None else defaults.get("max_tokens")
    return resolved_temp, resolved_tokens


def _build_error_response(request: LLMRequest, message: str, provider_name: str) -> LLMResponse:
    """Build a standardised error LLMResponse."""
    return LLMResponse(
        content="",
        model=request.model_name or "",
        provider=provider_name,
        request_id=request.request_id,
        error=message,
    )


class LLMService:
    """
    Unified service for all LLM interactions in AutoBot.

    Thin orchestration layer that sits above the ProviderRegistry and
    individual BaseProvider implementations.
    """

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self._registry = registry or get_provider_registry()
        self._request_count = 0
        self._error_count = 0
        # Shared response cache (L1 in-memory + L2 Redis) for clear_cache /
        # get_cache_metrics and the optimized chat path (#3185).
        self._response_cache = get_llm_cache()
        # Runtime provider override set via switch_provider() (#3185).
        self._active_provider: str | None = None
        # Tiered model routing — mirrors LLMInterface._init_tiered_routing() (#3185).
        try:
            self._tier_router: TieredModelRouter | None = TieredModelRouter(TierConfig.from_config())
        except Exception as exc:  # pragma: no cover
            logger.warning("Tiered routing init failed, disabled: %s", exc)
            self._tier_router = None

    # ------------------------------------------------------------------
    # Per-conversation model configuration
    # ------------------------------------------------------------------

    def set_conversation_provider(self, conversation_id: str, provider_name: str) -> None:
        """Pin a provider for all future requests in a conversation."""
        self._registry.set_conversation_provider(conversation_id, provider_name)

    def clear_conversation_provider(self, conversation_id: str) -> None:
        """Remove a per-conversation provider pin."""
        self._registry.clear_conversation_provider(conversation_id)

    # ------------------------------------------------------------------
    # Core inference interface
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        conversation_id: str | None = None,
        provider_name: str | None = None,
        model_name: str | None = None,
        llm_type: str | LLMType | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int = 60,
        use_cache: bool = True,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Execute a non-streaming chat completion.

        GH#8998: Supports quota-triggered fallback chains. When a model hits
        rate limit (429) or quota exceeded, automatically tries fallback models
        from the configured chain before failing.

        Args:
            messages: OpenAI-format message list
                (``[{"role": "user", "content": "…"}, …]``).
            conversation_id: Used to look up per-conversation provider/model
                overrides and pass through to cost tracking.
            provider_name: Optional explicit provider to use.
            model_name: Optional explicit model to request.
            llm_type: Task type (affects default temperature/max_tokens).
            temperature: Override temperature for this call.
            max_tokens: Override max_tokens for this call.
            timeout: Request timeout in seconds.
            use_cache: When True (default) a near-deterministic request may be
                served from / stored in the response cache (#10597).
            **kwargs: Additional fields forwarded to LLMRequest.

        Returns:
            LLMResponse.  ``response.error`` is set (non-empty) on failure.
        """
        self._request_count += 1
        start_time = time.time()
        resolved_type = _normalize_llm_type(llm_type)
        temp, tokens = _apply_task_defaults(resolved_type, temperature, max_tokens)

        # #10597: when the caller doesn't pin a model, optionally select one via
        # task-type/complexity routing (gated off by default; precision-sensitive).
        selected_model = model_name or self._select_chat_model(messages, resolved_type)

        request = LLMRequest(
            messages=messages,
            llm_type=resolved_type,
            model_name=selected_model,
            temperature=temp,
            max_tokens=tokens,
            timeout=timeout,
            **kwargs,
        )

        # #10597: serve identical requests from the L1/L2 response cache before
        # hitting any provider — but only when the request is safely reusable:
        # caching off, streaming, tool/structured/thinking calls, or
        # higher-temperature (non-deterministic) requests are never cached.
        cache_key: str | None = None
        if self._is_cacheable(request, temp, use_cache):
            cached, cache_key = await self._optimized_check_cache(
                messages,
                selected_model or "",
                provider_name or "auto",
                request.request_id,
                start_time,
                temperature=temp,
                max_tokens=tokens,
            )
            if cached is not None:
                self._calculate_cache_hit_rate(cached)
                return cached

        # GH#8998: Track attempted models to avoid infinite loops
        attempted_models = []
        fallback_manager = get_fallback_chain_manager()
        current_provider_name = provider_name
        current_model = selected_model
        max_fallback_attempts = 10  # Safety limit

        while len(attempted_models) < max_fallback_attempts:
            provider = await self._registry.get_provider_for_request(
                provider_name=current_provider_name,
                conversation_id=conversation_id,
            )
            if provider is None:
                self._error_count += 1
                logger.error("No available provider for chat request")
                return _build_error_response(request, "No available LLM provider", "none")

            # Update request with current model
            request.model_name = current_model

            # Track this attempt
            attempt_key = f"{provider.provider_name}:{current_model or 'default'}"
            if attempt_key in attempted_models:
                # Avoid infinite loop - this model was already tried
                logger.warning(
                    "Fallback chain loop detected at %s, breaking",
                    attempt_key,
                )
                break
            attempted_models.append(attempt_key)

            logger.debug(
                "Attempting chat completion with %s (attempt %d/%d)",
                attempt_key,
                len(attempted_models),
                max_fallback_attempts,
            )

            response = await provider.chat_completion(request)

            # Success case
            if not response.error:
                if len(attempted_models) > 1:
                    logger.info(
                        "Fallback successful: %s worked after %d attempts (tried: %s)",
                        attempt_key,
                        len(attempted_models),
                        " → ".join(attempted_models),
                    )
                    # GH#8998 - MVA-2999: Track successful fallback in Redis
                    primary_attempt = attempted_models[0]
                    primary_provider_name = primary_attempt.split(":")[0]
                    primary_model_name = primary_attempt.split(":", 1)[1] if ":" in primary_attempt else ""
                    self._track_fallback_event(
                        conversation_id=conversation_id,
                        primary_model=primary_model_name,
                        fallback_model=current_model or "",
                        primary_provider=primary_provider_name,
                        fallback_provider=provider.provider_name,
                    )
                # #10597: cache successful responses for identical future requests.
                if cache_key and response.content:
                    await self._optimized_store_cache(cache_key, response, request.request_id)
                self._track_usage(response, conversation_id)
                return response

            # GH#8998: Check if this is a rate limit error that should trigger fallback
            is_rate_limited, retry_after = extract_rate_limit_info(response)

            if is_rate_limited:
                # Try to find a fallback model
                fallback_result = fallback_manager.get_next_fallback(
                    current_model or provider.provider_name,
                    provider.provider_name,
                )

                if fallback_result:
                    next_model, next_provider = fallback_result
                    logger.info(
                        "Rate limit hit on %s, falling back to %s:%s",
                        attempt_key,
                        next_provider or current_provider_name,
                        next_model,
                    )
                    current_model = next_model
                    # #10601: when the fallback stays on the same (rate-limited)
                    # provider, honor the server-suggested Retry-After (capped)
                    # before retrying instead of hammering it immediately.
                    same_provider = (not next_provider) or next_provider == current_provider_name
                    if next_provider:
                        current_provider_name = next_provider
                    if retry_after and same_provider:
                        await asyncio.sleep(min(retry_after, _MAX_RETRY_AFTER_SECONDS))
                    continue
                else:
                    logger.warning(
                        "Rate limit hit on %s but no fallback chain configured, returning error",
                        attempt_key,
                    )

            # Non-rate-limit error or no fallback available
            self._error_count += 1
            logger.warning(
                "Provider %s returned error: %s (attempted: %s)",
                provider.provider_name,
                response.error,
                " → ".join(attempted_models),
            )
            self._track_usage(response, conversation_id)
            return response

        # Max attempts reached
        self._error_count += 1
        logger.error(
            "Exhausted fallback chain after %d attempts: %s",
            len(attempted_models),
            " → ".join(attempted_models),
        )
        return _build_error_response(
            request,
            f"All fallback models exhausted ({len(attempted_models)} attempts)",
            attempted_models[-1] if attempted_models else "none",
        )

    async def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        conversation_id: str | None = None,
        provider_name: str | None = None,
        model_name: str | None = None,
        llm_type: str | LLMType | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int = 120,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Stream a chat completion, yielding text chunks.

        GH#8998: Supports quota-triggered fallback chains. When a model hits
        rate limit (429) or quota exceeded, automatically tries fallback models
        from the configured chain before failing.

        Args are identical to ``chat()``.

        Yields:
            String chunks of the generated response.

        Raises:
            RuntimeError: if no provider is available or all fallbacks exhausted.
        """
        self._request_count += 1
        resolved_type = _normalize_llm_type(llm_type)
        temp, tokens = _apply_task_defaults(resolved_type, temperature, max_tokens)

        request = LLMRequest(
            messages=messages,
            llm_type=resolved_type,
            model_name=model_name,
            temperature=temp,
            max_tokens=tokens,
            stream=True,
            timeout=timeout,
            **kwargs,
        )

        # GH#8998: Track attempted models to avoid infinite loops
        attempted_models = []
        fallback_manager = get_fallback_chain_manager()
        current_provider_name = provider_name
        current_model = model_name
        max_fallback_attempts = 10  # Safety limit

        while len(attempted_models) < max_fallback_attempts:
            provider = await self._registry.get_provider_for_request(
                provider_name=current_provider_name,
                conversation_id=conversation_id,
            )
            if provider is None:
                self._error_count += 1
                raise RuntimeError("No available LLM provider for streaming request")

            # Update request with current model
            request.model_name = current_model

            # Track this attempt
            attempt_key = f"{provider.provider_name}:{current_model or 'default'}"
            if attempt_key in attempted_models:
                # Avoid infinite loop - this model was already tried
                logger.warning(
                    "Fallback chain loop detected at %s, breaking",
                    attempt_key,
                )
                break
            attempted_models.append(attempt_key)

            logger.debug(
                "Attempting stream completion with %s (attempt %d/%d)",
                attempt_key,
                len(attempted_models),
                max_fallback_attempts,
            )

            try:
                chunks_yielded = False
                async for chunk in provider.stream_completion(request):
                    chunks_yielded = True
                    yield chunk

                # Success - stream completed without errors
                if len(attempted_models) > 1:
                    logger.info(
                        "Fallback successful: %s worked after %d attempts (tried: %s)",
                        attempt_key,
                        len(attempted_models),
                        " → ".join(attempted_models),
                    )
                    # GH#8998 - MVA-2999: Track successful fallback in Redis
                    primary_attempt = attempted_models[0]
                    primary_provider_name = primary_attempt.split(":")[0]
                    primary_model_name = primary_attempt.split(":", 1)[1] if ":" in primary_attempt else ""
                    self._track_fallback_event(
                        conversation_id=conversation_id,
                        primary_model=primary_model_name,
                        fallback_model=current_model or "",
                        primary_provider=primary_provider_name,
                        fallback_provider=provider.provider_name,
                    )
                return

            except Exception as exc:
                # If we already yielded chunks, we can't retry - raise immediately
                if chunks_yielded:
                    self._error_count += 1
                    logger.error(
                        "Stream error from provider %s after yielding chunks: %s",
                        provider.provider_name,
                        exc,
                    )
                    raise

                # Check if this is a rate limit error that should trigger fallback
                error_str = str(exc).lower()
                is_rate_limited = (
                    "429" in error_str
                    or "rate limit" in error_str
                    or "quota" in error_str
                    or "too many requests" in error_str
                )

                if is_rate_limited:
                    # Try to find a fallback model
                    fallback_result = fallback_manager.get_next_fallback(
                        current_model or provider.provider_name,
                        provider.provider_name,
                    )

                    if fallback_result:
                        next_model, next_provider = fallback_result
                        logger.info(
                            "Rate limit hit on %s, falling back to %s:%s",
                            attempt_key,
                            next_provider or current_provider_name,
                            next_model,
                        )
                        current_model = next_model
                        if next_provider:
                            current_provider_name = next_provider
                        continue
                    else:
                        logger.warning(
                            "Rate limit hit on %s but no fallback chain configured",
                            attempt_key,
                        )

                # Non-rate-limit error or no fallback available
                self._error_count += 1
                logger.error(
                    "Stream error from provider %s: %s (attempted: %s)",
                    provider.provider_name,
                    exc,
                    " → ".join(attempted_models),
                )
                raise

        # Max attempts reached
        self._error_count += 1
        logger.error(
            "Exhausted fallback chain after %d attempts: %s",
            len(attempted_models),
            " → ".join(attempted_models),
        )
        raise RuntimeError(f"All fallback models exhausted ({len(attempted_models)} attempts)")

    # ------------------------------------------------------------------
    # Provider management helpers
    # ------------------------------------------------------------------

    async def list_providers(self) -> Dict[str, Any]:
        """Return registered providers and their availability status."""
        availability = await self._registry.health_check_all()
        providers = self._registry.list_providers()
        for entry in providers:
            entry["available"] = availability.get(str(entry["name"]), False)
        return {"providers": providers}

    async def list_models(self, provider_name: str | None = None) -> Dict[str, List[str]]:
        """
        Return available models, optionally filtered to a single provider.

        Returns a dict of ``{provider_name: [model_id, …]}``.
        """

        target_names = [provider_name] if provider_name else list(self._registry._providers.keys())
        results: Dict[str, List[str]] = {}
        for name in target_names:
            provider = self._registry._providers.get(name)
            if provider is None:
                continue
            try:
                results[name] = await provider.list_models()
            except Exception as exc:
                logger.warning("list_models failed for %s: %s", name, exc)
                results[name] = []
        return results

    def _track_fallback_event(
        self,
        conversation_id: str | None,
        primary_model: str,
        fallback_model: str,
        primary_provider: str,
        fallback_provider: str,
    ) -> None:
        """
        Track a successful fallback event in Redis.

        GH#8998 - MVA-2999: Store active fallback events in Redis with 1h TTL
        for visibility in the Admin UI.
        """
        try:
            redis_client = get_redis_client(database="main")
            fallback_key = f"llm:fallback:active:{conversation_id or 'system'}"

            event_data = {
                "conversation_id": conversation_id or "system",
                "primary_model": primary_model,
                "fallback_model": fallback_model,
                "primary_provider": primary_provider,
                "fallback_provider": fallback_provider,
                "timestamp": int(time.time()),
            }

            # Store with 1 hour TTL
            redis_client.setex(
                fallback_key,
                3600,  # 1 hour TTL
                json.dumps(event_data),
            )

            logger.debug(
                "Tracked fallback event: %s → %s (conversation: %s)",
                primary_model,
                fallback_model,
                conversation_id or "system",
            )
        except Exception as exc:
            logger.warning(
                "Failed to track fallback event in Redis: %s",
                exc,
                exc_info=True,
            )

    def get_stats(self) -> Dict[str, Any]:
        """Return service-level statistics."""
        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "registry": self._registry.get_stats(),
        }

    # ------------------------------------------------------------------
    # Optimized chat (vLLM prefix-cache variant) (#3185)
    # ------------------------------------------------------------------

    async def chat_optimized(
        self,
        agent_type: str,
        user_message: str,
        session_id: str,
        user_name: str | None = None,
        user_role: str | None = None,
        available_tools: List | None = None,
        recent_context: str | None = None,
        additional_params: Dict | None = None,
        **llm_params: Any,
    ) -> LLMResponse:
        """Chat completion with vLLM prefix-cache-optimised prompts.

        Builds a prefix-cache-friendly prompt (static base + dynamic suffix)
        and routes the request directly to vLLM.  Cache hit rate is attached
        to ``response.metadata["cache_hit_rate"]``.

        Ported from ``LLMInterface.chat_completion_optimized`` (interface.py
        line 1381).  Renamed to match the ``chat()`` / ``stream()`` naming
        convention already established on this class.

        Args:
            agent_type: Agent type string used to select the base prompt.
            user_message: The user's message content.
            session_id: Session identifier forwarded to the prompt builder.
            user_name: Optional user display name for the prompt.
            user_role: Optional user role for the prompt.
            available_tools: Optional list of tool names; defaults to the
                full tool registry when omitted.
            recent_context: Optional recent-context string for the prompt.
            additional_params: Optional extra params forwarded to the
                prompt builder.
            **llm_params: Additional fields forwarded to LLMRequest (e.g.
                ``temperature``, ``max_tokens``, ``stream``).

        Returns:
            LLMResponse.  ``response.metadata["cache_hit_rate"]`` is set when
            vLLM prefix-cache data is available in ``response.usage``.
        """
        from agent_tier_classifier import get_base_prompt_for_agent
        from prompt_manager import get_optimized_prompt
        from tools import get_tool_registry

        # Issue #5870: default to full registry when caller omits available_tools.
        if available_tools is None:
            available_tools = get_tool_registry().get_available_tools()

        tool_descriptions: Dict | None = None
        try:
            registry = get_tool_registry()
            tool_set = set(available_tools)
            uncompressed = {n: d for n, d in registry.get_raw_descriptions().items() if n in tool_set}
            compressed_map = await registry.get_compressed_descriptions()
            tool_descriptions = {n: d for n, d in compressed_map.items() if n in tool_set}
            uncompressed_bytes = sum(len(d) for d in uncompressed.values())
            compressed_bytes = sum(len(d) for d in tool_descriptions.values())
            saving_pct = (1 - compressed_bytes / uncompressed_bytes) * 100 if uncompressed_bytes else 0
            logger.debug(
                "[#5827] Tool desc savings: %d tools, %d → %d bytes (%.0f%% reduction)",
                len(tool_descriptions),
                uncompressed_bytes,
                compressed_bytes,
                saving_pct,
            )
        except Exception:
            logger.warning(
                "[#5827] compress_description failed; falling back to tool names only",
                exc_info=True,
            )

        system_prompt = get_optimized_prompt(
            base_prompt_key=get_base_prompt_for_agent(agent_type),
            session_id=session_id,
            user_name=user_name,
            user_role=user_role,
            available_tools=available_tools,
            recent_context=recent_context,
            additional_params=additional_params,
            tool_descriptions=tool_descriptions,
        )

        request_id: str = llm_params.pop("request_id", str(uuid.uuid4()))
        start_time = time.time()

        # Issue #4054: use the vLLM config key directly to avoid cache-key
        # collisions between Ollama and vLLM calls.
        try:
            from config.manager import get_config_manager as _get_cfg

            model_name: str = _get_cfg().get("llm.vllm.default_model", "meta-llama/Llama-3.2-3B-Instruct")
        except Exception:
            model_name = "meta-llama/Llama-3.2-3B-Instruct"

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Issue #3858: check L1/L2 cache before hitting vLLM.
        cache_key: str | None = None
        with _llm_tracer.start_as_current_span("llm.chat_optimized") as span:
            span.set_attribute("llm.provider", "vllm")
            span.set_attribute("llm.request_id", request_id)
            span.set_attribute("llm.agent_type", agent_type)

            if not llm_params.get("stream", False):
                cached, cache_key = await self._optimized_check_cache(
                    messages, model_name, "vllm", request_id, start_time
                )
                if cached is not None:
                    self._calculate_cache_hit_rate(cached)
                    span.set_attribute("llm.cached", True)
                    return cached

            self._request_count += 1
            request = LLMRequest(
                messages=messages,
                provider="vllm",  # type: ignore[arg-type]
                model_name=model_name,
                request_id=request_id,
                **llm_params,
            )

            provider = self._registry.get_provider_by_name("vllm")
            if provider is None:
                self._error_count += 1
                logger.error("vLLM provider not registered; chat_optimized cannot proceed")
                return _build_error_response(request, "vLLM provider not available", "vllm")

            try:
                response = await provider.chat_completion(request)
            except Exception as exc:
                self._error_count += 1
                logger.error("chat_optimized vLLM request failed: %s", exc)
                span.record_exception(exc)
                return _build_error_response(request, str(exc), "vllm")

            if response.error:
                self._error_count += 1
                logger.warning("chat_optimized vLLM error: %s", response.error)

            actual_model = response.model if response.model else model_name

            if cache_key and not response.error and response.content:
                await self._optimized_store_cache(cache_key, response, request_id)

            processing_time = time.time() - start_time
            if not response.processing_time:
                response.processing_time = processing_time

            self._calculate_cache_hit_rate(response)
            self._track_usage(response, session_id)

            span.set_attribute("llm.model", actual_model)
            span.set_attribute("llm.cached", False)
            span.set_attribute("llm.error", bool(response.error))
            return response

    # ------------------------------------------------------------------
    # Runtime provider control (#3185)
    # ------------------------------------------------------------------

    async def switch_provider(self, provider: str, model: str = "", validate: bool = False) -> Dict[str, Any]:
        """Switch the active LLM provider at runtime.

        Ported from ``LLMInterface.switch_provider`` (interface.py line 469).

        Args:
            provider: Provider name registered in the ProviderRegistry.
            model: Optional model identifier to store alongside the switch.
            validate: When True, run a health check before switching; the
                switch is aborted if the provider is unreachable.

        Returns:
            ``{"success": True, "provider": …, "model": …}`` on success, or
            ``{"success": False, "error": …, "available": […]}`` on failure.
        """
        registered = {entry["name"] for entry in self._registry.list_providers()}
        if provider not in registered:
            return {
                "success": False,
                "error": f"Unknown provider: {provider}",
                "available": sorted(registered),
            }

        if validate:
            health = await self._registry.health_check_all()
            if not health.get(provider, False):
                return {
                    "success": False,
                    "error": f"{provider} failed health check",
                }

        self._active_provider = provider
        if model:
            try:
                from config.manager import get_config_manager as _get_cfg

                _get_cfg().set("backend.llm.active_provider", provider)
                _get_cfg().set("backend.llm.active_model", model)
            except Exception as exc:
                logger.warning("Could not persist provider switch to config: %s", exc)

        logger.info("Switched LLM provider to %s (model=%s)", provider, model)
        return {"success": True, "provider": provider, "model": model}

    async def get_all_provider_status(self) -> Dict[str, Any]:
        """Return health and activity status for every registered provider.

        Ported from ``LLMInterface.get_all_provider_status`` (interface.py
        line 502).

        Returns:
            Dict mapping provider names to
            ``{"available": bool, "active": bool, "error": str | None}``.
        """
        health = await self._registry.health_check_all()
        statuses: Dict[str, Any] = {}
        for entry in self._registry.list_providers():
            name = str(entry["name"])
            available = health.get(name, False)
            statuses[name] = {
                "available": available,
                "active": name == self._active_provider,
                "error": None if available else f"{name} reported as unavailable",
            }
        return statuses

    # ------------------------------------------------------------------
    # Response cache management (#3185)
    # ------------------------------------------------------------------

    def get_cache_metrics(self) -> Dict[str, Any]:
        """Return detailed L1/L2 cache performance metrics.

        Ported from ``LLMInterface.get_cache_metrics`` (interface.py line 1341).

        Returns:
            Dict with L1/L2 hit rates, sizes, and request counts.
        """
        return self._response_cache.get_metrics()

    async def clear_cache(self, l1: bool = True, l2: bool = True) -> Dict[str, int]:
        """Flush the L1 in-memory and/or L2 Redis response caches.

        Ported from ``LLMInterface.clear_cache`` (interface.py line 1352).

        Args:
            l1: Clear the L1 in-memory LRU cache.
            l2: Clear the L2 Redis cache.

        Returns:
            Dict with counts of cleared entries per tier, e.g.
            ``{"l1_cleared": 42, "l2_cleared": 7}``.
        """
        result: Dict[str, int] = {}
        if l1:
            result["l1_cleared"] = self._response_cache.clear_l1()
        if l2:
            result["l2_cleared"] = await self._response_cache.clear_l2()
        return result

    # ------------------------------------------------------------------
    # Tiered routing (#3185, ported from LLMInterface._init_tiered_routing)
    # ------------------------------------------------------------------

    @property
    def tier_router(self) -> TieredModelRouter | None:
        """Return the shared TieredModelRouter instance, or None if disabled.

        Callers in api/llm.py reach this to get/set metrics and config.
        Mirrors ``LLMInterface._tier_router`` (interface.py line 410).
        """
        return self._tier_router

    # ------------------------------------------------------------------
    # Full performance metrics (#3185, ported from LLMInterface.get_metrics)
    # ------------------------------------------------------------------

    def get_metrics(self) -> Dict[str, Any]:
        """Return aggregated performance metrics for this service.

        Shape mirrors ``LLMInterface.get_metrics()`` (interface.py line 1322)
        so callers in ``api/llm_optimization.py`` can access the same keys.
        LLMService does not own the LLMInterface-specific optimization objects
        (rate-limiter, optimization-router, connection-pool), so those keys
        are reported as empty dicts.  All other keys are populated from live
        data.

        Keys returned:
            total_requests, cache_hits, cache_misses, avg_response_time,
            fallback_count, provider_usage, cache (L1/L2 detail),
            tiered_routing (when enabled), optimization (empty dict).
        """
        cache_metrics = self.get_cache_metrics()
        registry_stats = self._registry.get_stats()
        metrics: Dict[str, Any] = {
            "total_requests": self._request_count,
            "cache_hits": cache_metrics.get("l1_hits", 0) + cache_metrics.get("l2_hits", 0),
            "cache_misses": cache_metrics.get("misses", 0),
            "avg_response_time": 0.0,
            "fallback_count": 0,
            "provider_usage": registry_stats.get("providers", {}),
            "cache": cache_metrics,
            # LLMInterface-specific optimization objects not present on LLMService.
            "optimization": {},
        }
        if self._tier_router:
            metrics["tiered_routing"] = self._tier_router.get_metrics()
        return metrics

    # ------------------------------------------------------------------
    # Provider routing map (#3185, ported from LLMInterface.provider_routing)
    # ------------------------------------------------------------------

    @property
    def provider_routing(self) -> Dict[str, Any]:
        """Return a mapping of provider name to provider object.

        Mirrors ``LLMInterface.provider_routing`` (interface.py line 282).
        Callers in ``api/llm_providers.py`` check ``provider_name in
        llm.provider_routing`` to validate provider existence before testing.
        """
        return dict(self._registry._providers)

    # ------------------------------------------------------------------
    # Provider health check (#3185, ported from LLMInterface._is_provider_healthy)
    # ------------------------------------------------------------------

    async def is_provider_healthy(self, provider_name: str) -> tuple[bool, str | None]:
        """Check whether a named provider is currently healthy.

        Public equivalent of ``LLMInterface._is_provider_healthy()``
        (interface.py line 1094).  Uses ``ProviderHealthManager`` when
        available; falls back to ``registry.health_check_all()`` otherwise.

        Args:
            provider_name: Registered provider name to check.

        Returns:
            ``(is_healthy, error_message_or_None)``.
        """
        if _HEALTH_CHECK_AVAILABLE and provider_name in ("ollama", "openai"):
            try:
                health_result = await ProviderHealthManager.check_provider_health(
                    provider_name, timeout=2.0, use_cache=True
                )
                if health_result.status == ProviderStatus.UNAVAILABLE:
                    return (
                        False,
                        f"{provider_name} unavailable: {health_result.message}",
                    )
            except Exception as exc:
                logger.debug("Health check for %s raised: %s", provider_name, exc)
            return True, None

        # Fallback: use the registry's cached health check
        try:
            health = await self._registry.health_check_all()
            is_healthy = health.get(provider_name, True)
            if not is_healthy:
                return False, f"{provider_name} reported as unavailable"
        except Exception as exc:
            logger.debug("Registry health_check_all for %s raised: %s", provider_name, exc)
        return True, None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_cacheable(self, request: LLMRequest, temperature: float, use_cache: bool) -> bool:
        """Whether a chat request may be served from / stored in the cache (#10597).

        Only near-deterministic, safely-reusable requests qualify: caching must
        be enabled, the response cache present, and the request must not stream,
        use tools, force structured output, request extended thinking, or run at
        a temperature above the configured determinism threshold.
        """
        if not (use_cache and config.llm_response_cache and self._response_cache is not None):
            return False
        if request.stream or request.structured_output:
            return False
        if getattr(request, "tools", None) or getattr(request, "tool_choice", None):
            return False
        if request.metadata.get("api_kwargs"):  # extended-thinking / provider-specific knobs
            return False
        return temperature is not None and temperature <= config.llm_cache_max_temperature

    def _select_chat_model(self, messages: List[Dict[str, str]], resolved_type: LLMType) -> str | None:
        """Pick a model when the caller didn't pin one (#10597).

        Gated behind ``config.chat_tiered_routing`` (default off) because model
        downgrade is precision-sensitive — enable only after rag_benchmarks
        validation.  Returns None to fall through to the registry default.
        """
        if not config.chat_tiered_routing:
            return None
        # Task-type pin: classification/extraction are reliably cheap tasks.
        cheap = {
            LLMType.CLASSIFICATION: config.classification_model,
            LLMType.EXTRACTION: config.light_processing_model,
        }.get(resolved_type)
        if cheap:
            return cheap
        # Otherwise defer to complexity-based tier routing.
        if self._tier_router is not None:
            try:
                selected, _ = self._tier_router.route(messages)
                return selected or None
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Tier routing failed, using registry default: %s", exc)
        return None

    def _calculate_cache_hit_rate(self, response: LLMResponse) -> None:
        """Attach vLLM prefix-cache hit rate to response metadata.

        Mirrors ``LLMInterface._calculate_cache_hit_rate`` (interface.py
        line 1372).  No-ops when the response has no cached_tokens in usage.
        """
        if not response.usage or "cached_tokens" not in response.usage:
            return
        cached_tokens = response.usage.get("cached_tokens", 0)
        total_tokens = response.usage.get("prompt_tokens", 0)
        hit_rate = (cached_tokens / total_tokens * 100) if total_tokens > 0 else 0.0
        response.metadata["cache_hit_rate"] = hit_rate

    async def _optimized_check_cache(
        self,
        messages: List[Dict[str, str]],
        model_name: str,
        provider: str,
        request_id: str,
        start_time: float,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> tuple:
        """Look up L1/L2 cache for a chat request.

        Mirrors the cache-check block in ``LLMInterface._check_cache``
        (interface.py line 765).  Shared by ``chat()`` (#10597) and the
        optimized vLLM path; ``temperature`` and ``max_tokens`` are part of the
        cache key so calls differing only in those don't collide.

        Returns:
            ``(LLMResponse, cache_key)`` on hit; ``(None, cache_key)`` on miss.
        """
        cache_key = self._response_cache.generate_cache_key(
            messages=messages,
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        cached = await self._response_cache.get(cache_key)
        if cached is not None:
            processing_time = time.time() - start_time
            logger.debug("Cache hit for optimized request %s", request_id[:8])
            return (
                LLMResponse(
                    content=cached.content,
                    model=cached.model,
                    provider=provider,
                    processing_time=processing_time,
                    request_id=request_id,
                    cached=True,
                    metadata=cached.metadata or {},
                ),
                cache_key,
            )
        return None, cache_key

    async def _optimized_store_cache(self, cache_key: str, response: LLMResponse, request_id: str) -> None:
        """Store a successful optimized-chat response in the L1/L2 cache."""
        await self._response_cache.set(
            cache_key,
            CachedResponse(
                content=response.content,
                model=response.model,
                tokens_used=response.tokens_used,
                processing_time=response.processing_time,
                metadata={"request_id": request_id},
            ),
        )

    def _track_usage(self, response: LLMResponse, conversation_id: str | None) -> None:
        """Forward usage data to the cost tracker when available."""
        if not response.usage:
            return
        try:
            from services.llm_cost_tracker import LLMCostTracker

            tracker = LLMCostTracker()
            tracker.record(
                provider=response.provider,
                model=response.model,
                usage=response.usage,
                conversation_id=conversation_id,
            )
        except Exception as exc:
            logger.debug("Cost tracking skipped: %s", exc)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_service_instance: LLMService | None = None


def get_llm_service() -> LLMService:
    """Return the process-level LLMService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = LLMService()
    return _service_instance


__all__ = ["LLMService", "get_llm_service"]
