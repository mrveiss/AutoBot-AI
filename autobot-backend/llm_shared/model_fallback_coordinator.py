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
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

from .fallback_chain import get_fallback_chain_manager
from .fallback_events import emit_fallback_event
from .headroom_routing import exhausted_window
from .models import LLMRequest, LLMResponse
from .optimization.rate_limiter import RateLimitError
from .provider_degradation import AllCredentialsNeedReauthError, get_degradation_store

if TYPE_CHECKING:
    from .provider_registry import ProviderRegistry

logger = get_logger(__name__)

_MAX_FALLBACK_ATTEMPTS: int = env_int("AUTOBOT_MAX_FALLBACK_ATTEMPTS", 3)

REASON_RATE_LIMIT = "rate_limit_429"
#: Pre-emptive switch on observed headroom (#15028) -- no 429 was paid for.
REASON_HEADROOM_PREEMPT = "headroom_preempt"


class _FallbackTrail:
    """Why each fallback hop of one request happened -- the audit trail (#15028)."""

    def __init__(self) -> None:
        self.reasons: list[str] = []
        self.preempted: list[dict] = []

    @property
    def reason(self) -> str:
        """The reason of the most recent hop (reactive 429 until a hop says otherwise)."""
        return self.reasons[-1] if self.reasons else REASON_RATE_LIMIT

    def note_preempt(self, hop: "_PreemptiveSwitch", from_model: str) -> None:
        logger.info(
            "headroom-preempt: %r window %r near-exhausted -- switching %r -> %r before dispatch",
            hop.provider,
            hop.window,
            from_model,
            hop.next_model,
        )
        self.reasons.append(REASON_HEADROOM_PREEMPT)
        self.preempted.append(
            {"from_model": from_model, "from_provider": hop.provider, "window": hop.window,
             "to_model": hop.next_model, "to_provider": hop.next_provider}
        )  # fmt: skip


class _FallbackRun:
    """Mutable state of one ``execute_with_fallback`` call: where it started, where it is now, how it got there."""

    def __init__(self, request: LLMRequest) -> None:
        self.request = request
        self.primary_model = request.model_name or ""
        self.primary_provider = request.provider.value if request.provider else None
        self.model = self.primary_model
        self.provider = self.primary_provider
        self.chain_tried: list[str] = [self.model] if self.model else []
        self.last_error: LLMResponse | None = None
        self.trail = _FallbackTrail()

    def switch_to(self, model: str, provider: Optional[str]) -> None:
        """Move the request onto the next model of the chain."""
        self.model, self.provider = model, provider
        self.chain_tried.append(model)
        self.request = ModelFallbackCoordinator._clone_with_model(self.request, model, provider)

    def audit(self, attempt_count: int, *, fallback_used: bool, exhausted: bool = False) -> dict:
        """Keyword arguments for ``ModelFallbackCoordinator._annotate``."""
        return {
            "fallback_used": fallback_used,
            "primary_model": self.primary_model,
            "current_model": self.model,
            "attempt_count": attempt_count,
            "chain_tried": self.chain_tried,
            "exhausted": exhausted,
            "degraded_skipped": self.request.metadata.get("degraded_skipped"),
            "reason": self.trail.reason,
            "preempted": self.trail.preempted,
        }


class _PreemptiveSwitch(Exception):
    """Internal: the selected provider is near-exhausted and a fallback has room (#15028)."""

    def __init__(self, provider: str, window: str, next_model: str, next_provider: Optional[str]) -> None:
        super().__init__(f"{provider} window {window!r} near-exhausted")
        self.provider = provider
        self.window = window
        self.next_model = next_model
        self.next_provider = next_provider


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

        run = _FallbackRun(request)
        for attempt in range(max_attempts + 1):
            try:
                # Last attempt never hops: an all-exhausted chain can't cycle (#15028).
                guard = self._headroom_guard(run.model, run.chain_tried) if attempt < max_attempts else None
                response = await self._dispatch(run.request, registry, hop_guard=guard)
                await self._finish_success(run, response, attempt)
                return response
            except _PreemptiveSwitch as hop:
                run.trail.note_preempt(hop, run.model)
                run.switch_to(hop.next_model, hop.next_provider)
            except RateLimitError as exc:
                if not await self._on_rate_limit(run, exc, attempt, max_attempts):
                    break

        # All fallbacks exhausted.
        assert run.last_error is not None
        self._annotate(run.last_error, **run.audit(len(run.chain_tried), fallback_used=True, exhausted=True))
        await self._emit(run, exhausted=True)
        return run.last_error

    async def _finish_success(self, run: "_FallbackRun", response: LLMResponse, attempt: int) -> None:
        """Annotate the audit metadata of a successful response and announce any fallback."""
        fallback_used = attempt > 0
        self._annotate(response, **run.audit(attempt + 1, fallback_used=fallback_used))
        if not fallback_used:
            return
        logger.info(
            "quota-fallback: request succeeded on attempt %d using model=%r (primary=%r) chain=%s",
            attempt + 1,
            run.model,
            run.primary_model,
            run.chain_tried,
        )
        await self._emit(run)

    async def _on_rate_limit(self, run: "_FallbackRun", exc: RateLimitError, attempt: int, max_attempts: int) -> bool:
        """Handle a 429 that survived backoff: mark the provider, pick the next model.

        Returns True when the loop should retry on the fallback, False when the chain is exhausted.
        """
        run.last_error = LLMResponse(content="", model=run.model, provider=run.provider or "", error=str(exc))
        # Mark the exhausted provider:model degraded so sibling workers skip it immediately
        # (Issue #11519), using the provider the registry actually resolved at dispatch time --
        # the request may carry none. Marked before the max-attempts break so the final provider is too.
        failed_provider = run.request.metadata.get("selected_provider") or run.provider
        if failed_provider:
            await get_degradation_store().mark_degraded(failed_provider, run.model or None)
        else:
            logger.debug("degradation: provider unresolved for model=%r — mark skipped", run.model)
        if attempt >= max_attempts:
            logger.warning(
                "quota-fallback: all %d fallback attempts exhausted for model=%r", max_attempts, run.primary_model
            )
            return False
        fallback = get_fallback_chain_manager().get_next_fallback(run.model, run.provider)
        if fallback is None:
            logger.warning("quota-fallback: no fallback registered for model=%r provider=%r", run.model, run.provider)
            return False
        logger.info(
            "quota-fallback: model=%r hit rate limit (attempt %d), switching to fallback model=%r provider=%r",
            run.model,
            attempt + 1,
            *fallback,
        )
        run.trail.reasons.append(REASON_RATE_LIMIT)
        run.switch_to(*fallback)
        return True

    @staticmethod
    async def _emit(run: "_FallbackRun", *, exhausted: bool = False) -> None:
        """Publish the PROVIDER_FALLBACK event for *run* (reactive 429 or pre-emptive switch)."""
        await emit_fallback_event(
            conversation_id=run.request.metadata.get("conversation_id"),
            primary_model=run.primary_model,
            fallback_model=run.model,
            primary_provider=run.primary_provider,
            fallback_provider=run.provider,
            chain_tried=run.chain_tried,
            degraded_skipped=run.request.metadata.get("degraded_skipped"),
            exhausted=exhausted,
            reason=run.trail.reason,
            request_id=run.request.request_id,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _dispatch(
        request: LLMRequest,
        registry: "ProviderRegistry",
        *,
        hop_guard: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> LLMResponse:
        """Select provider for *request* and call chat_completion, raising on rate limit.

        *hop_guard* (#15028) sees the resolved provider name before the call and
        may raise ``_PreemptiveSwitch``; ``None`` is exactly the reactive path.
        """
        provider_name: Optional[str] = request.provider.value if request.provider else None
        try:
            provider = await registry.get_provider_for_request(provider_name=provider_name, request=request)
        except AllCredentialsNeedReauthError as exc:
            # Not a rate limit: no fallback hop can help, and retrying is futile (#15022).
            return LLMResponse(content="", error=str(exc), model=request.model_name or "")
        if provider is None:
            return LLMResponse(
                content="",
                error="All providers unavailable",
                model=request.model_name or "",
            )
        if hop_guard is not None:
            await hop_guard(request.metadata.get("selected_provider") or provider.provider_name)
        # BaseProvider.chat_completion() raises RateLimitError when backoff exhausted.
        return await provider.chat_completion(request)

    @staticmethod
    def _headroom_guard(current_model: str, chain_tried: list[str]) -> Callable[[str], Awaitable[None]]:
        """Build the pre-dispatch check: switch only if observed headroom says so AND a fallback has room."""

        async def _guard(provider: str) -> None:
            entry = await exhausted_window(provider)
            if entry is None:
                return  # no (fresh) headroom data: today's reactive path, untouched
            manager = get_fallback_chain_manager()
            visited, model, owner = set(chain_tried), current_model, provider
            while (nxt := manager.get_next_fallback(model, owner)) is not None and nxt[0] not in visited:
                visited.add(nxt[0])
                if nxt[1] is None or await exhausted_window(nxt[1]) is None:
                    raise _PreemptiveSwitch(provider, entry.window, nxt[0], nxt[1])
                model, owner = nxt[0], nxt[1]

        return _guard

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
        degraded_skipped: list[str] | None = None,
        reason: str = REASON_RATE_LIMIT,
        preempted: list[dict] | None = None,
    ) -> None:
        """Extend response.provider_metadata with fallback audit fields (+ ``preemptive_switches`` when any, #15028)."""
        if response.provider_metadata is None:
            response.provider_metadata = {}
        response.fallback_used = fallback_used
        response.provider_metadata.update(
            {
                "fallback_used": fallback_used,
                "primary_model": primary_model,
                "fallback_model": current_model if fallback_used else None,
                "fallback_reason": reason if fallback_used else None,
                "attempt_count": attempt_count,
                "fallback_chain_tried": chain_tried,
                "fallback_exhausted": exhausted,
                "degraded_skipped": degraded_skipped or [],
                **({"preemptive_switches": list(preempted)} if preempted else {}),
            }
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

get_fallback_coordinator = lazy_singleton(ModelFallbackCoordinator)


__all__ = ["ModelFallbackCoordinator", "get_fallback_coordinator"]
