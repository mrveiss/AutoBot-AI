# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Model-level fallback coordinator — wire fallback_chain + rate_limit_backoff
into actual call flow. (GH#8998)

When a provider returns a 429/quota error and backoff retries are exhausted,
this coordinator tries the next model in the configured fallback chain before
surfacing the error to the caller.

Architecture:
  Caller → execute_with_fallback() → provider.chat_completion()
                                       ↓ RateLimitError after backoff
                                    get_fallback_chain_manager().get_next_fallback()
                                       ↓ (model, provider) pair
                                    switch request to fallback model → retry

Audit trail: populated into LLMResponse.provider_metadata and logged at INFO
so ops dashboards can detect quota pressure before users notice.
"""

from __future__ import annotations

import copy
import os
from typing import TYPE_CHECKING, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

from .fallback_chain import get_fallback_chain_manager
from .models import LLMRequest, LLMResponse
from .optimization.rate_limiter import RateLimitError

if TYPE_CHECKING:
    from .provider_registry import ProviderRegistry

logger = get_logger(__name__)

_MAX_FALLBACK_ATTEMPTS: int = int(os.environ.get("AUTOBOT_MAX_FALLBACK_ATTEMPTS", "3"))


class ModelFallbackCoordinator:
    """
    Coordinates model-level fallback on quota/rate limit exhaustion.

    Usage::

        coordinator = get_fallback_coordinator()
        response = await coordinator.execute_with_fallback(request, registry)

    The coordinator is stateless — the same singleton is safe for concurrent
    requests across all uvicorn workers.
    """

    async def execute_with_fallback(
        self,
        request: LLMRequest,
        registry: "ProviderRegistry",
        *,
        max_attempts: int = _MAX_FALLBACK_ATTEMPTS,
    ) -> LLMResponse:
        """
        Execute *request* with automatic model fallback on rate limit.

        Tries the primary model first. On RateLimitError, queries the fallback
        chain manager for the next model and retries, up to *max_attempts*
        total fallback hops. Returns the first successful response or the last
        error response when all fallbacks are exhausted.

        The returned LLMResponse.provider_metadata is extended with::

            {
                "fallback_used": True | False,
                "primary_model": "claude-opus-4",
                "fallback_model": "claude-sonnet-4",   # only when fallback triggered
                "fallback_reason": "rate_limit_429",
                "attempt_count": 2,
                "fallback_chain_tried": ["claude-opus-4", "claude-sonnet-4"],
            }
        """
        if not request.fallback_enabled:
            return await self._dispatch(request, registry)

        primary_model = request.model_name or ""
        primary_provider = request.provider.value if request.provider else None
        current_model = primary_model
        current_provider = primary_provider
        chain_tried: list[str] = [current_model] if current_model else []
        last_error_response: LLMResponse | None = None

        for attempt in range(max_attempts + 1):
            try:
                response = await self._dispatch(request, registry)
                # Success — annotate audit metadata and return.
                fallback_used = attempt > 0
                self._annotate(
                    response,
                    fallback_used=fallback_used,
                    primary_model=primary_model,
                    current_model=current_model,
                    attempt_count=attempt + 1,
                    chain_tried=chain_tried,
                )
                if fallback_used:
                    logger.info(
                        "quota-fallback: request succeeded on attempt %d " "using model=%r (primary=%r) chain=%s",
                        attempt + 1,
                        current_model,
                        primary_model,
                        chain_tried,
                    )
                return response

            except RateLimitError as exc:
                last_error_response = LLMResponse(
                    content="",
                    model=current_model,
                    provider=current_provider or "",
                    error=str(exc),
                )
                if attempt >= max_attempts:
                    logger.warning(
                        "quota-fallback: all %d fallback attempts exhausted for model=%r",
                        max_attempts,
                        primary_model,
                    )
                    break

                fallback = get_fallback_chain_manager().get_next_fallback(current_model, current_provider)
                if fallback is None:
                    logger.warning(
                        "quota-fallback: no fallback registered for model=%r provider=%r",
                        current_model,
                        current_provider,
                    )
                    break

                next_model, next_provider = fallback
                logger.info(
                    "quota-fallback: model=%r hit rate limit (attempt %d), "
                    "switching to fallback model=%r provider=%r",
                    current_model,
                    attempt + 1,
                    next_model,
                    next_provider,
                )
                current_model = next_model
                current_provider = next_provider
                chain_tried.append(current_model)
                request = self._clone_with_model(request, next_model, next_provider)

        # All fallbacks exhausted.
        assert last_error_response is not None
        self._annotate(
            last_error_response,
            fallback_used=True,
            primary_model=primary_model,
            current_model=current_model,
            attempt_count=len(chain_tried),
            chain_tried=chain_tried,
            exhausted=True,
        )
        return last_error_response

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _dispatch(request: LLMRequest, registry: "ProviderRegistry") -> LLMResponse:
        """Select provider for *request* and call chat_completion, raising on rate limit."""
        provider_name: Optional[str] = request.provider.value if request.provider else None
        provider = await registry.get_provider_for_request(provider_name=provider_name, request=request)
        if provider is None:
            return LLMResponse(
                content="",
                error="All providers unavailable",
                model=request.model_name or "",
            )
        # BaseProvider.chat_completion() raises RateLimitError when backoff exhausted.
        return await provider.chat_completion(request)

    @staticmethod
    def _clone_with_model(
        request: LLMRequest,
        model: str,
        provider_name: Optional[str],
    ) -> LLMRequest:
        """Return a shallow copy of *request* with updated model/provider."""
        cloned = copy.copy(request)
        cloned.model_name = model
        if provider_name:
            from .models import ProviderType

            try:
                cloned.provider = ProviderType(provider_name.lower())
            except ValueError:
                cloned.provider = None
        else:
            cloned.provider = None
        return cloned

    @staticmethod
    def _annotate(
        response: LLMResponse,
        *,
        fallback_used: bool,
        primary_model: str,
        current_model: str,
        attempt_count: int,
        chain_tried: list[str],
        exhausted: bool = False,
    ) -> None:
        """Extend response.provider_metadata with fallback audit fields."""
        if response.provider_metadata is None:
            response.provider_metadata = {}
        response.fallback_used = fallback_used
        response.provider_metadata.update(
            {
                "fallback_used": fallback_used,
                "primary_model": primary_model,
                "fallback_model": current_model if fallback_used else None,
                "fallback_reason": "rate_limit_429" if fallback_used else None,
                "attempt_count": attempt_count,
                "fallback_chain_tried": chain_tried,
                "fallback_exhausted": exhausted,
            }
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

get_fallback_coordinator = lazy_singleton(ModelFallbackCoordinator)


__all__ = ["ModelFallbackCoordinator", "get_fallback_coordinator"]
