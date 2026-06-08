# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MCP Span Tracing (Issue #4413)

Lightweight span-level tracing for MCPProcessManager.  Every tool call
produces an MCPSpan that is written asynchronously to Redis.

Key schema
----------
- ``mcp_trace:{trace_id}``          → MCPSpan JSON, TTL 3600 s
- ``mcp_trace_idx:{skill_name}``    → sorted-set of trace_ids scored by
                                      started_at timestamp, TTL 3600 s

The write is fire-and-forget (``asyncio.create_task``).  Redis errors are
swallowed and logged at DEBUG level so tracing never disrupts tool calls.
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

_SPAN_TTL: int = 3600  # seconds
_MAX_PARAM_BYTES: int = 4096  # 4 KB cap for input_params before Redis storage


def _truncate_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Truncate input_params if serialized size exceeds _MAX_PARAM_BYTES."""
    serialized = json.dumps(params, default=str)
    if len(serialized.encode("utf-8")) <= _MAX_PARAM_BYTES:
        return params
    return {
        "_truncated": True,
        "preview": serialized.encode("utf-8")[:_MAX_PARAM_BYTES].decode("utf-8", errors="replace"),
    }


@dataclass
class MCPSpan:
    """Immutable record of a single MCP tool-call invocation."""

    trace_id: str
    skill_name: str
    tool_name: str
    started_at: float
    ended_at: float | None
    input_params: Dict[str, Any]
    output: Dict[str, Any] | None
    error: str | None
    pid: int


def new_span(
    skill_name: str,
    tool_name: str,
    input_params: Dict[str, Any],
    pid: int,
) -> MCPSpan:
    """Create a new MCPSpan with a fresh trace_id and current timestamp."""
    return MCPSpan(
        trace_id=str(uuid.uuid4()),
        skill_name=skill_name,
        tool_name=tool_name,
        started_at=time.time(),
        ended_at=None,
        input_params=_truncate_params(input_params),
        output=None,
        error=None,
        pid=pid,
    )


async def write_span(span: MCPSpan) -> None:
    """Write *span* to Redis.  Silently swallows all errors (DEBUG log only)."""
    try:
        redis = await get_async_redis_client(database="main")
        if redis is None:
            logger.debug("mcp_trace: Redis unavailable, dropping span %s", span.trace_id)
            return

        payload = json.dumps(asdict(span), ensure_ascii=False)
        span_key = f"mcp_trace:{span.trace_id}"
        idx_key = f"mcp_trace_idx:{span.skill_name}"

        pipe = redis.pipeline()
        pipe.set(span_key, payload, ex=_SPAN_TTL)
        pipe.zadd(idx_key, {span.trace_id: span.started_at})
        pipe.expire(idx_key, _SPAN_TTL)
        await pipe.execute()

        logger.debug(
            "mcp_trace: wrote span trace_id=%s skill=%s tool=%s",
            span.trace_id,
            span.skill_name,
            span.tool_name,
        )
    except Exception as exc:
        logger.debug("mcp_trace: failed to write span %s: %s", span.trace_id, exc)
