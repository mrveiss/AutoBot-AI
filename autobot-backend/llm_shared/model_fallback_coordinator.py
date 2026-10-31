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

from .failover_policy import hold_seconds, locality_allows
from .fallback_chain import FallbackHop, get_fallback_chain_manager
from .fallback_events import emit_fallback_event
from .headroom_routing import exhausted_window
from .models import LLMRequest, LLMResponse
from .optimization.rate_limiter import RateLimitError
from .provider_auth import ProviderAuthError
from .provider_degradation import AllCredentialsNeedReauthError, get_degradation_store
from .provider_error_category import (
    ProviderErrorCategory,
    ProviderFailure,
    classify_provider_error,
    failure_from_exception,
    failure_from_response,
)

if TYPE_CHECKING:
    from .provider_registry import ProviderRegistry

logger = get_logger(__name__)

_MAX_FALLBACK_ATTEMPTS: int = env_int("AUTOBOT_MAX_FALLBACK_ATTEMPTS", 3)

REASON_RATE_LIMIT = "rate_limit_429"
#: Pre-emptive switch on observed headroom (#15028) -- no 429 was paid for.
REASON_HEADROOM_PREEMPT = "headroom_preempt"


def _reason_for(category: ProviderErrorCategory) -> str:
    """The audit/event reason of a hop: the historic 429 string for a throttle, else the category."""
    return REASON_RATE_LIMIT if category is ProviderErrorCategory.RATE_LIMIT else category.value


class _ProviderFailureError(Exception):
    """Internal: a provider answered with a failover-eligible error response (#19753)."""

    def __init__(self, failure: ProviderFailure, response: LLMResponse) -> None:
        super().__init__(failure.message)
        self.failure = failure
        self.response = response


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
        return await self._run_loop(_FallbackRun(request), registry, max_attempts, first_attempt=0)

    async def fail_over(
        self,
        request: LLMRequest,
        registry: "ProviderRegistry",
        failure: ProviderFailure,
        *,
        acted: bool,
        held: bool = False,
        max_attempts: int = _MAX_FALLBACK_ATTEMPTS,
    ) -> LLMResponse | None:
        """Continue *request* on the next model after a caller's own dispatch of it failed (#19753).

        For a caller that already made the first call itself -- the streaming chat path, which posts
        to the provider directly. ``None`` means "do not fail over, surface the original error":
        the turn already ``acted`` (emitted text or ran a tool, so a retry could replay a side
        effect), the failure is not failover-eligible, or no permitted model is left. Otherwise
        the request runs on the chain exactly as :meth:`execute_with_fallback` runs it, so the
        once-per-model rule, the skip window / quota hold and the locality rule are the same.
        ``held`` says the model was already held out when the call was skipped, so it is not
        marked again -- re-marking on every message would stretch a skip window without end.
        """
        if acted or not failure.category.failover_eligible or max_attempts < 1:
            logger.info("failover: not attempted (acted=%s category=%s)", acted, failure.category.value)
            return None
        run = _FallbackRun(request)
        run.last_error = LLMResponse(content="", model=run.model, provider=run.provider or "", error=failure.message)
        if not await self._on_failure(run, failure, 0, max_attempts, mark=not held):
            return None
        return await self._run_loop(run, registry, max_attempts, first_attempt=1)

    async def _run_loop(
        self, run: "_FallbackRun", registry: "ProviderRegistry", max_attempts: int, *, first_attempt: int
    ) -> LLMResponse:
        """Dispatch ``run.request``, hopping down the chain on a failover-eligible failure."""
        for attempt in range(first_attempt, max_attempts + 1):
            try:
                # Last attempt never hops: an all-exhausted chain can't cycle (#15028).
                guard = self._headroom_guard(run.model, run.chain_tried) if attempt < max_attempts else None
                response = await self._dispatch(run.request, registry, hop_guard=guard, raise_failures=True)
                await self._finish_success(run, response, attempt)
                return response
            except _PreemptiveSwitch as hop:
                run.trail.note_preempt(hop, run.model)
                run.switch_to(hop.next_model, hop.next_provider)
            except (RateLimitError, _ProviderFailureError, ProviderAuthError) as exc:
                if not await self._on_failure(run, self._record_failure(run, exc), attempt, max_attempts):
                    break

        # All fallbacks exhausted.
        assert run.last_error is not None
        self._annotate(run.last_error, **run.audit(len(run.chain_tried), fallback_used=True, exhausted=True))
        await self._emit(run, exhausted=True)
        return run.last_error

    @staticmethod
    def _record_failure(run: "_FallbackRun", exc: Exception) -> ProviderFailure:
        """Keep the failed attempt's response as the run's last error; return its classified failure."""
        if isinstance(exc, _ProviderFailureError):
            run.last_error = exc.response
            return exc.failure
        run.last_error = LLMResponse(content="", model=run.model, provider=run.provider or "", error=str(exc))
        if isinstance(exc, RateLimitError):
            return ModelFallbackCoordinator._rate_limit_failure(exc)
        return failure_from_exception(exc)

    @staticmethod
    def _rate_limit_failure(exc: RateLimitError) -> ProviderFailure:
        """A backoff-exhausted 429 is a throttle, or a plan limit when its text says so."""
        failure = classify_provider_error(str(exc), getattr(exc, "retry_after", None))
        if failure.category is ProviderErrorCategory.BILLING:
            return failure
        return ProviderFailure(ProviderErrorCategory.RATE_LIMIT, failure.message, failure.retry_after)

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

    async def _on_failure(
        self, run: "_FallbackRun", failure: ProviderFailure, attempt: int, max_attempts: int, *, mark: bool = True
    ) -> bool:
        """Hold the failed model out, then pick the next usable one.

        Returns True when the loop should retry on the fallback, False when the chain is exhausted.
        """
        if mark:
            await self._mark_failed(run, failure)
        if attempt >= max_attempts:
            logger.warning(
                "quota-fallback: all %d fallback attempts exhausted for model=%r", max_attempts, run.primary_model
            )
            return False
        hop = await self._next_usable_hop(run)
        if hop is None:
            logger.warning("quota-fallback: no usable fallback for model=%r provider=%r", run.model, run.provider)
            return False
        logger.info(
            "quota-fallback: model=%r failed (%s, attempt %d), switching to fallback model=%r provider=%r",
            run.model,
            failure.category.value,
            attempt + 1,
            hop.model,
            hop.provider,
        )
        run.trail.reasons.append(_reason_for(failure.category))
        run.switch_to(hop.model, hop.provider)
        return True

    @staticmethod
    async def _mark_failed(run: "_FallbackRun", failure: ProviderFailure) -> None:
        """Mark the failed provider:model degraded so sibling workers skip it (Issue #11519).

        A transient failure is skipped for the degradation window; a plan/quota limit is held until
        the provider's reset (#19753). Uses the provider the registry actually resolved at dispatch
        time -- the request may carry none. Marked before the max-attempts break so the final one is too.
        """
        failed_provider = run.request.metadata.get("selected_provider") or run.provider
        if not failed_provider:
            logger.debug("degradation: provider unresolved for model=%r — mark skipped", run.model)
            return
        ttl = hold_seconds(failure)
        extra = {"ttl_seconds": ttl} if ttl else {}
        await get_degradation_store().mark_degraded(failed_provider, run.model or None, **extra)

    @staticmethod
    async def _next_usable_hop(run: "_FallbackRun") -> FallbackHop | None:
        """The next chain hop that is untried, not held out, and allowed to receive this prompt.

        Each model is tried at most once per request (``chain_tried``). A hop that would move the
        prompt from a local provider to an external one is skipped unless the operator wrote the chain.
        """
        manager, store = get_fallback_chain_manager(), get_degradation_store()
        tried = {m.lower() for m in run.chain_tried}
        from_provider = run.request.metadata.get("selected_provider") or run.provider
        model, owner = run.model, run.provider
        while (hop := manager.get_next_hop(model, owner)) is not None and hop.model.lower() not in tried:
            tried.add(hop.model.lower())
            allowed = locality_allows(from_provider, hop.provider, operator_configured=hop.operator_configured)
            if allowed and not (hop.provider and await store.is_degraded(hop.provider, hop.model)):
                return hop
            model, owner = hop.model, hop.provider
        return None

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
        raise_failures: bool = False,
    ) -> LLMResponse:
        """Select provider for *request* and call chat_completion, raising on rate limit.

        *raise_failures* (#19753) also raises for a failover-eligible error response; off, it is returned as before.
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
            return LLMResponse(content="", error="All providers unavailable", model=request.model_name or "")
        if hop_guard is not None:
            await hop_guard(request.metadata.get("selected_provider") or provider.provider_name)
        # BaseProvider.chat_completion() raises RateLimitError when backoff exhausted.
        response = await provider.chat_completion(request)
        if raise_failures:
            ModelFallbackCoordinator._raise_if_failover_eligible(response)
        return response

    @staticmethod
    def _raise_if_failover_eligible(response: LLMResponse) -> None:
        """Raise ``_ProviderFailureError`` for an error response a different model could answer (#19753)."""
        failure = failure_from_response(response)
        if failure is not None and failure.category.failover_eligible:
            raise _ProviderFailureError(failure, response)

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
