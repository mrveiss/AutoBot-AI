# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fallback-chain mechanics shared by LLMService.chat()/stream() (GH#8998).

Split out of services/llm_service.py (#16526/#620 — the file's recorded
line-count ceiling, #14236, may not grow; extraction kept llm_service.py's
own extraction for prompt-compression/concurrency wiring from pushing it
over). Every function here is stateless with respect to LLMService — no
``self`` — so moving them costs nothing but an import: each took only
explicit arguments already.

``LLMService.chat()``/``stream()`` still own the fallback LOOP (attempted
models, current_model/current_provider_name, the 10-attempt ceiling) and the
per-attempt orchestration (``_attempt_chat_once``/``_attempt_stream_once``,
which also touch instance state — the cache, ``_error_count``,
``_track_usage`` — and so stay on LLMService itself); this module owns only
the one-shot mechanics each attempt calls into.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, List

from autobot_shared.env_utils import env_float
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_constants import TTL_1_HOUR
from llm_shared.fallback_events import emit_fallback_event

logger = get_logger(__name__)

# Cap on honoring a provider-suggested Retry-After before a same-provider retry,
# so a hostile/huge value can't stall the request indefinitely (#10601).
# Mirrors the constant llm_service.py carried before this extraction.
_MAX_RETRY_AFTER_SECONDS = env_float("AUTOBOT_LLM_MAX_RETRY_AFTER_SECONDS", 30)


class StreamRetry(Exception):
    """Internal: carries the next (model, provider) stream() should retry
    with after a rate-limited error that occurred before any chunk was
    yielded (see LLMService._attempt_stream_once)."""

    def __init__(self, next_model: str | None, next_provider: str | None) -> None:
        super().__init__("stream retry")
        self.next_model = next_model
        self.next_provider = next_provider


async def resolve_attempt_provider(
    registry: Any, current_provider_name: str | None, conversation_id: str | None
) -> Any:
    """Resolve the provider for one fallback-chain attempt; shared by
    chat()/stream()."""
    return await registry.get_provider_for_request(provider_name=current_provider_name, conversation_id=conversation_id)


def track_attempt(
    attempted_models: List[str],
    provider: Any,
    current_model: str | None,
    max_fallback_attempts: int,
    label: str,
) -> str | None:
    """Record + debug-log one fallback-chain attempt; shared by chat()/stream().

    Returns the attempt key, or None when this (provider, model) pair was
    already tried — the caller must break out of its loop.
    """
    attempt_key = f"{provider.provider_name}:{current_model or 'default'}"
    if attempt_key in attempted_models:
        # Avoid infinite loop - this model was already tried
        logger.warning("Fallback chain loop detected at %s, breaking", attempt_key)
        return None
    attempted_models.append(attempt_key)
    logger.debug(
        "Attempting %s with %s (attempt %d/%d)", label, attempt_key, len(attempted_models), max_fallback_attempts
    )
    return attempt_key


def track_fallback_event(
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
            TTL_1_HOUR,
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


async def emit_exhausted_fallback(
    conversation_id: str | None,
    attempted_models: list,
    current_model: str | None,
    request_id: str,
) -> None:
    """Emit PROVIDER_FALLBACK(exhausted=True). #11995: chat()/stream() never
    tracked the exhaustion case at all (only successful fallbacks were)."""
    primary_attempt = attempted_models[0]
    primary_provider_name = primary_attempt.split(":")[0]
    primary_model_name = primary_attempt.split(":", 1)[1] if ":" in primary_attempt else ""
    await emit_fallback_event(
        conversation_id=conversation_id,
        primary_model=primary_model_name,
        fallback_model=current_model,
        primary_provider=primary_provider_name,
        fallback_provider=attempted_models[-1].split(":")[0],
        chain_tried=list(attempted_models),
        exhausted=True,
        request_id=request_id,
    )


async def emit_fallback_success(
    conversation_id: str | None,
    attempted_models: List[str],
    attempt_key: str,
    current_model: str | None,
    provider: Any,
    request_id: str,
) -> None:
    """Log + Redis-track (GH#8998 - MVA-2999) + emit PROVIDER_FALLBACK for a
    successful fallback; shared by chat()/stream(). No-ops when the first
    attempt succeeded (nothing fell back).
    """
    if len(attempted_models) <= 1:
        return
    logger.info(
        "Fallback successful: %s worked after %d attempts (tried: %s)",
        attempt_key,
        len(attempted_models),
        " → ".join(attempted_models),
    )
    primary_attempt = attempted_models[0]
    primary_provider_name = primary_attempt.split(":")[0]
    primary_model_name = primary_attempt.split(":", 1)[1] if ":" in primary_attempt else ""
    track_fallback_event(
        conversation_id=conversation_id,
        primary_model=primary_model_name,
        fallback_model=current_model or "",
        primary_provider=primary_provider_name,
        fallback_provider=provider.provider_name,
    )
    await emit_fallback_event(
        conversation_id=conversation_id,
        primary_model=primary_model_name,
        fallback_model=current_model,
        primary_provider=primary_provider_name,
        fallback_provider=provider.provider_name,
        chain_tried=list(attempted_models),
        request_id=request_id,
    )


async def apply_rate_limit_fallback(
    fallback_manager: Any,
    attempt_key: str,
    current_model: str | None,
    current_provider_name: str | None,
    provider: Any,
    retry_after: float | None = None,
) -> tuple[str | None, str | None] | None:
    """Resolve the next fallback model/provider on a rate-limited response;
    shared by chat()/stream().

    #10601: when ``retry_after`` is given and the fallback stays on the same
    provider, honors the server-suggested Retry-After (capped) before the
    caller retries.

    Returns the new ``(current_model, current_provider_name)`` to continue
    the loop with, or None when no fallback chain is configured.
    """
    fallback_result = fallback_manager.get_next_fallback(
        current_model or provider.provider_name,
        provider.provider_name,
    )
    if not fallback_result:
        logger.warning(
            "Rate limit hit on %s but no fallback chain configured, returning error",
            attempt_key,
        )
        return None

    next_model, next_provider = fallback_result
    logger.info(
        "Rate limit hit on %s, falling back to %s:%s",
        attempt_key,
        next_provider or current_provider_name,
        next_model,
    )
    same_provider = (not next_provider) or next_provider == current_provider_name
    if next_provider:
        current_provider_name = next_provider
    if retry_after and same_provider:
        await asyncio.sleep(min(retry_after, _MAX_RETRY_AFTER_SECONDS))
    return next_model, current_provider_name


__all__ = [
    "StreamRetry",
    "resolve_attempt_provider",
    "track_attempt",
    "track_fallback_event",
    "emit_exhausted_fallback",
    "emit_fallback_success",
    "apply_rate_limit_fallback",
]
