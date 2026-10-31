# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider failover for the streaming chat path (#19753).

``_process_single_llm_iteration`` posts straight to the provider and streams the reply. When that
call fails, the turn is handed to ``ModelFallbackCoordinator.fail_over`` -- the one fallback stack --
but only while the **not-acted guard** holds: the turn has emitted no text and run no tool. Past that
point a retry could replay a side effect or show a second, different answer, so the error is surfaced.

Where "acted" is decided, in order of when it becomes true:

1. ``iteration > 1`` or a non-empty ``execution_history`` -- an earlier iteration already streamed and/or ran tools.
2. a non-error message already in ``ctx.workflow_messages`` -- something was shown before the first LLM call.
3. ``emitted`` below -- this iteration yielded a chunk before it failed.

A model the user picked by hand (``model_override``) never fails over: its error is surfaced.

Images: the only image on this path is the last tool screenshot (``_extract_latest_tool_screenshot``),
read from ``execution_history``; a turn that has one has run a tool, so it is already "acted" and
surfaces. ``LLMRequest`` has no image field, so an image could not be carried to a backup anyway.

What the backup request carries: the system prompt, the prompt, and ``temperature`` / ``top_p`` as the
primary's own payload sets them. Not carried: ``num_ctx`` (an Ollama option), ``api_kwargs`` (thinking
budgets, ``betas`` and effort parameters are provider-specific payload fields, not ``LLMRequest`` fields),
and the image. Neither path redacts the prompt (redaction is for logs and traces only), so the backup
receives exactly the text the primary did.

Default chains name only hosted model families (``claude-*``, ``gpt-*``), so an Ollama chat model has a
chain only from an operator's ``AUTOBOT_FALLBACK_CHAIN_*`` variable; without one a failure is surfaced.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Optional

import aiohttp

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import CategoryDefaults
from llm_shared import get_provider_registry
from llm_shared.model_fallback_coordinator import get_fallback_coordinator
from llm_shared.models import LLMRequest, LLMResponse
from llm_shared.provider_degradation import get_degradation_store
from llm_shared.provider_error_category import (
    ProviderErrorCategory,
    ProviderFailure,
    failure_from_exception,
    failure_from_status,
)
from llm_shared.types import LLMType, ProviderType

from .models import LLMIterationContext

logger = get_logger(__name__)

#: Raised by the transport while connecting or reading -- the "network" and "timeout" failures.
TRANSPORT_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError)


@dataclass(frozen=True)
class IterationCall:
    """What the failover needs to know about one LLM iteration."""

    manager: Any
    ctx: LLMIterationContext
    iteration: int
    prompt: str


def turn_has_acted(ctx: LLMIterationContext, iteration: int) -> bool:
    """The not-acted guard, before this iteration streams anything (see the module docstring)."""
    if iteration > 1 or ctx.execution_history:
        return True
    return any(getattr(m, "type", "") != "error" for m in ctx.workflow_messages)


def _service_failure(item: Any) -> Optional[ProviderFailure]:
    """The failure carried by ``_create_llm_service_error``'s message, else ``None``."""
    metadata = getattr(item, "metadata", None) or {}
    status = metadata.get("status_code")
    if getattr(item, "type", "") == "error" and metadata.get("error") and status is not None:
        return failure_from_status(int(status))
    return None


def _build_request(call: IterationCall) -> LLMRequest:
    """The same prompt the primary got, as a registry request for the failed model."""
    ctx = call.ctx
    options = call.manager._get_llm_request_payload(ctx.selected_model, call.prompt, ctx.system_prompt or "")["options"]
    system = [{"role": CategoryDefaults.ROLE_SYSTEM, "content": ctx.system_prompt}] if ctx.system_prompt else []
    return LLMRequest(
        messages=[*system, {"role": CategoryDefaults.ROLE_USER, "content": call.prompt}],
        llm_type=LLMType.CHAT,
        provider=ProviderType.OLLAMA,
        model_name=ctx.selected_model,
        temperature=options["temperature"],
        top_p=options["top_p"],
        metadata={"conversation_id": ctx.session_id},
    )


async def _recover(call: IterationCall, failure: ProviderFailure, *, acted: bool, held: bool) -> Optional[LLMResponse]:
    """Ask the coordinator for the answer from the next model; ``None`` = surface the original error."""
    try:
        response = await get_fallback_coordinator().fail_over(
            _build_request(call), get_provider_registry(), failure, acted=acted, held=held
        )
    except Exception:
        logger.exception(
            "failover: the fallback attempt itself failed; surfacing the original %s error", failure.category.value
        )
        return None
    if response is None or response.error or not response.content:
        return None
    return response


async def _hand_picked(call: IterationCall) -> bool:
    """True when the user chose this model by hand: the session's ``model_override`` (#11585)."""
    session = await call.manager.get_or_create_session(call.ctx.session_id)
    return bool((session.metadata or {}).get("model_override"))


async def _primary_is_held(call: IterationCall) -> bool:
    """True while the primary sits in its skip window / quota hold and the user did not pick it by hand."""
    if not await get_degradation_store().is_degraded(ProviderType.OLLAMA.value, call.ctx.selected_model):
        return False
    return not await _hand_picked(call)


async def _recovered_items(call: IterationCall, response: LLMResponse) -> AsyncIterator[Any]:
    """The recovered answer as the chunk + ``(text, tool_calls)`` the streaming path would have produced."""
    manager, ctx = call.manager, call.ctx
    meta = response.provider_metadata or {}
    message = manager._init_streaming_message(
        "response", response.model or ctx.selected_model, ctx.terminal_session_id, ctx.used_knowledge, ctx.rag_citations
    )
    message.stream(response.content)
    message.merge_metadata(
        {
            "failover": {
                "from_model": ctx.selected_model,
                "to_model": response.model,
                "reason": meta.get("fallback_reason"),
                "to_provider": meta.get("fallback_provider"),
                "operator_configured": meta.get("operator_configured"),
            }
        }
    )
    yield message.to_workflow_message()
    yield (
        response.content,
        await manager._log_and_parse_tool_calls(response.content, call.iteration, ctx.terminal_session_id, {}),
    )


async def _held_primary_items(call: IterationCall) -> Optional[list]:
    """Items from the next model when the primary is held out, else ``None`` (try the primary)."""
    if turn_has_acted(call.ctx, call.iteration) or not await _primary_is_held(call):
        return None
    failure = ProviderFailure(ProviderErrorCategory.PROVIDER_UNAVAILABLE, "primary held out of rotation")
    response = await _recover(call, failure, acted=False, held=True)
    return None if response is None else [item async for item in _recovered_items(call, response)]


async def _failure_items(call: IterationCall, failure: ProviderFailure, *, emitted: bool) -> Optional[list]:
    """Items from the next model after the primary failed, or ``None`` to surface the original error."""
    acted = emitted or turn_has_acted(call.ctx, call.iteration)
    if not acted and await _hand_picked(call):
        logger.info("failover: %s failure on a hand-picked model -- surfaced, no hop", failure.category.value)
        return None
    response = await _recover(call, failure, acted=acted, held=False)
    return None if response is None else [item async for item in _recovered_items(call, response)]


async def stream_with_failover(call: IterationCall, open_stream: Callable[[], AsyncIterator]) -> AsyncIterator:
    """Run one LLM iteration; on a pre-output provider failure, answer from the next model instead.

    *open_stream* is not called at all while the primary is held out. A failure after text was yielded,
    or on a turn that already ran a tool, is surfaced as before: the service-error message, or the re-raise.
    """
    held_items = await _held_primary_items(call)
    if held_items is not None:
        for item in held_items:
            yield item
        return
    emitted = False
    stream = open_stream()
    try:
        async for item in stream:
            failure = None if emitted else _service_failure(item)
            recovered = await _failure_items(call, failure, emitted=emitted) if failure else None
            if recovered is not None:
                await stream.aclose()
                for out in recovered:
                    yield out
                return
            emitted = emitted or not isinstance(item, tuple)
            yield item
    except TRANSPORT_ERRORS as exc:
        recovered = None if emitted else await _failure_items(call, failure_from_exception(exc), emitted=emitted)
        if recovered is None:
            raise
        for out in recovered:
            yield out
