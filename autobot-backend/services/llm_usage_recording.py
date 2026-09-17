# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Record an :class:`LLMResponse`'s token usage against the cost tracker.

Extracted from ``LLMService._track_usage`` (#16845), which called
``LLMCostTracker.record(provider=..., model=..., usage=..., conversation_id=...)``
-- a method the tracker has never defined. Every call raised ``AttributeError``
into ``except Exception: logger.debug(...)``, so from ``eda3f4529e`` (2026-04-01)
the main chat path recorded no spend at all and said so only at debug level.
Budget Policy's hard stop reads the records written here, so it could not fire
for chat traffic either.

This lives in its own module rather than on ``LLMService`` so the OpenAI- and
Anthropic-compatible gateways record through the same path instead of growing a
third copy of the conversion.

**Token key contract.** ``LLMResponse.usage`` is OpenAI-shaped:
``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``. Providers speaking
another dialect normalise before building the response -- Ollama maps
``prompt_eval_count``/``eval_count`` in
``llm_shared/providers/ollama_provider.py`` -- and every other reader in the tree
assumes the same two keys, e.g.
``llm_shared/observability/prometheus_observer.py``. Reading any other key here
would record zeros while looking fixed.

**Three outcomes stay distinguishable**, because collapsing them is exactly how
the original defect stayed invisible for five months:

* no usage block at all -- the provider reported nothing; normal, silent.
* a usage block carrying neither token key -- a provider contract change; warned.
* the tracker call failed -- a defect; logged with a traceback at error level.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from llm_shared.models import LLMResponse
from services.llm_cost_tracker import get_cost_tracker

logger = get_logger(__name__)

INPUT_TOKEN_KEY = "prompt_tokens"
OUTPUT_TOKEN_KEY = "completion_tokens"


def token_counts(usage: Dict[str, Any]) -> tuple[int, int] | None:
    """``(input, output)`` from a usage block, or ``None`` when it has neither key.

    A block carrying only one of the two is still usable -- the missing side is
    genuinely zero for that call -- so only the both-absent case is unreadable.
    """
    input_tokens = usage.get(INPUT_TOKEN_KEY)
    output_tokens = usage.get(OUTPUT_TOKEN_KEY)
    if input_tokens is None and output_tokens is None:
        return None
    return int(input_tokens or 0), int(output_tokens or 0)


async def record_response_usage(
    response: LLMResponse,
    session_id: str | None = None,
    *,
    user_id: str | None = None,
    agent_id: str | None = None,
    endpoint: str | None = None,
) -> None:
    """Persist ``response``'s token usage so cost and budget policy can see it.

    Best-effort with respect to the caller: a tracker failure is logged, never
    raised, since it must not turn a served completion into an error. It is
    logged at error level with a traceback -- the point of #16845 is that this
    failing has to be visible to someone, which ``logger.debug`` was not.
    """
    usage = response.usage or {}
    if not usage:
        return
    counts = token_counts(usage)
    if counts is None:
        logger.warning(
            "Usage block from %s/%s carries neither %s nor %s (keys: %s); no spend recorded",
            response.provider or "unknown",
            response.model or "unknown",
            INPUT_TOKEN_KEY,
            OUTPUT_TOKEN_KEY,
            sorted(usage),
        )
        return
    input_tokens, output_tokens = counts
    try:
        await get_cost_tracker().track_usage(
            provider=response.provider,
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            endpoint=endpoint,
            latency_ms=response.processing_time * 1000 if response.processing_time else None,
            success=not response.error,
            error_message=response.error,
        )
    except Exception:
        logger.exception(
            "Cost tracking failed for %s/%s: %d in / %d out unrecorded, and budget policy cannot see this spend",
            response.provider or "unknown",
            response.model or "unknown",
            input_tokens,
            output_tokens,
        )
