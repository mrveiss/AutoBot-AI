# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from llm_interface_pkg.models import LLMRequest, LLMResponse
from llm_interface_pkg.types import LLMType, ProviderType
from llm_providers.provider_registry import ProviderRegistry, get_provider_registry

logger = logging.getLogger(__name__)

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


def _normalize_llm_type(llm_type: Union[str, LLMType, None]) -> LLMType:
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
    temperature: Optional[float],
    max_tokens: Optional[int],
) -> tuple[float, Optional[int]]:
    """
    Return (temperature, max_tokens) with task-type defaults filled in.

    Explicit caller values always take priority.
    """
    defaults = _TASK_TYPE_DEFAULTS.get(llm_type.value, _TASK_TYPE_DEFAULTS["general"])
    resolved_temp = temperature if temperature is not None else defaults["temperature"]
    resolved_tokens = max_tokens if max_tokens is not None else defaults.get("max_tokens")
    return resolved_temp, resolved_tokens


def _build_error_response(
    request: LLMRequest, message: str, provider_name: str
) -> LLMResponse:
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

    def __init__(self, registry: Optional[ProviderRegistry] = None) -> None:
        self._registry = registry or get_provider_registry()
        self._request_count = 0
        self._error_count = 0

    # ------------------------------------------------------------------
    # Per-conversation model configuration
    # ------------------------------------------------------------------

    def set_conversation_provider(
        self, conversation_id: str, provider_name: str
    ) -> None:
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
        conversation_id: Optional[str] = None,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        llm_type: Union[str, LLMType, None] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Execute a non-streaming chat completion.

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
            **kwargs: Additional fields forwarded to LLMRequest.

        Returns:
            LLMResponse.  ``response.error`` is set (non-empty) on failure.
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
            timeout=timeout,
            **kwargs,
        )

        provider = await self._registry.get_provider_for_request(
            provider_name=provider_name,
            conversation_id=conversation_id,
        )
        if provider is None:
            self._error_count += 1
            logger.error("No available provider for chat request")
            return _build_error_response(
                request, "No available LLM provider", "none"
            )

        response = await provider.chat_completion(request)
        if response.error:
            self._error_count += 1
            logger.warning(
                "Provider %s returned error: %s", provider.provider_name, response.error
            )
        self._track_usage(response, conversation_id)
        return response

    async def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        conversation_id: Optional[str] = None,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        llm_type: Union[str, LLMType, None] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: int = 120,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Stream a chat completion, yielding text chunks.

        Args are identical to ``chat()``.

        Yields:
            String chunks of the generated response.

        Raises:
            RuntimeError: if no provider is available.
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

        provider = await self._registry.get_provider_for_request(
            provider_name=provider_name,
            conversation_id=conversation_id,
        )
        if provider is None:
            self._error_count += 1
            raise RuntimeError("No available LLM provider for streaming request")

        try:
            async for chunk in provider.stream_completion(request):
                yield chunk
        except Exception as exc:
            self._error_count += 1
            logger.error(
                "Stream error from provider %s: %s", provider.provider_name, exc
            )
            raise

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

    async def list_models(
        self, provider_name: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """
        Return available models, optionally filtered to a single provider.

        Returns a dict of ``{provider_name: [model_id, …]}``.
        """
        import asyncio as _asyncio

        target_names = (
            [provider_name]
            if provider_name
            else list(self._registry._providers.keys())
        )
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

    def get_stats(self) -> Dict[str, Any]:
        """Return service-level statistics."""
        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "registry": self._registry.get_stats(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _track_usage(
        self, response: LLMResponse, conversation_id: Optional[str]
    ) -> None:
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

_service_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Return the process-level LLMService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = LLMService()
    return _service_instance


__all__ = ["LLMService", "get_llm_service"]
