# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical PROVIDER_FALLBACK event emission (#11995, GH#8998).

Single shared seam called from BOTH divergent fallback paths —
``model_fallback_coordinator.ModelFallbackCoordinator.execute_with_fallback``
and ``services.llm_service.LLMService``'s inline ``chat()``/``stream()``
fallback loops — so neither call site is inert (cf. the
agentloop_inert_in_production doctrine: features wired into only one path
are effectively hidden).

This module intentionally does NOT touch Redis persistence: the existing
``llm:fallback:active:*`` write in ``services/llm_service.py`` and its reader
(``GET /api/llm/fallback-status`` in ``api/llm_providers.py``, added by
PR #9421 / MVA-2999) are left as-is. This helper adds the missing real-time
signal on top of that already-wired read path.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from events.bus import publish_event
from events.event_types import PROVIDER_FALLBACK

logger = get_logger(__name__)


def _build_fallback_payload(
    *,
    conversation_id: Optional[str],
    primary_model: str,
    fallback_model: Optional[str],
    primary_provider: Optional[str],
    fallback_provider: Optional[str],
    reason: str,
    chain_tried: Optional[List[str]],
    degraded_skipped: Optional[List[str]],
    exhausted: bool,
    request_id: Optional[str],
) -> Dict[str, Any]:
    """Assemble the canonical PROVIDER_FALLBACK payload shape (#11995)."""
    return {
        "conversation_id": conversation_id or "system",
        "request_id": request_id,
        "primary_model": primary_model,
        "primary_provider": primary_provider,
        "fallback_model": fallback_model,
        "fallback_provider": fallback_provider,
        "reason": reason,
        "chain_tried": chain_tried or [],
        "degraded_skipped": degraded_skipped or [],
        "exhausted": exhausted,
        "timestamp": time.time(),
    }


async def emit_fallback_event(
    *,
    conversation_id: Optional[str],
    primary_model: str,
    fallback_model: Optional[str],
    primary_provider: Optional[str] = None,
    fallback_provider: Optional[str] = None,
    reason: str = "rate_limit_429",
    chain_tried: Optional[List[str]] = None,
    degraded_skipped: Optional[List[str]] = None,
    exhausted: bool = False,
    request_id: Optional[str] = None,
) -> None:
    """Publish a PROVIDER_FALLBACK event to the "global" channel.

    Non-fatal on failure (same pattern as rag_service._emit_retrieval_feedback):
    observability must never break the request it is describing.
    """
    payload = _build_fallback_payload(
        conversation_id=conversation_id,
        primary_model=primary_model,
        fallback_model=fallback_model,
        primary_provider=primary_provider,
        fallback_provider=fallback_provider,
        reason=reason,
        chain_tried=chain_tried,
        degraded_skipped=degraded_skipped,
        exhausted=exhausted,
        request_id=request_id,
    )
    try:
        await publish_event("global", PROVIDER_FALLBACK, payload)
    except Exception as exc:
        logger.debug("PROVIDER_FALLBACK publish failed (non-fatal): %s", exc)


__all__ = ["emit_fallback_event"]
