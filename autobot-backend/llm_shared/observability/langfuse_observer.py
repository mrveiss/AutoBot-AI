# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LangFuseObserver — record LLM inference traces in LangFuse (GH#9012).

Import guard: the `langfuse` package is optional.  The backend starts cleanly
when the package is absent and the LANGFUSE_* env vars are not set.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.logging_manager import get_logger

from .tracing_config import LangFuseTracingConfig

logger = get_logger(__name__)


class LangFuseObserver:
    """Emit a LangFuse generation record for every LLM inference call."""

    def __init__(self, config: LangFuseTracingConfig) -> None:
        try:
            from langfuse import Langfuse
        except ImportError as exc:
            raise RuntimeError(
                "langfuse package not installed — run: pip install langfuse>=2.0.0"
            ) from exc

        self._client = Langfuse(
            host=config.host,
            public_key=config.public_key,
            secret_key=config.secret_key,
        )
        self._pending: dict[str, Any] = {}

    async def on_request(self, request, metadata: dict) -> None:
        self._evict_overflow()
        gen = self._client.generation(
            trace_id=request.metadata.get("run_id", request.request_id),
            name="llm.inference",
            model=request.model_name or "",
            input=request.messages,
            metadata={
                "agent_id": request.metadata.get("agent_id"),
                "run_id": request.metadata.get("run_id"),
                "llm_type": str(request.llm_type),
            },
        )
        self._pending[request.request_id] = gen

    async def on_response(self, response, latency_ms: float, cost: float) -> None:
        gen = self._pending.pop(response.request_id, None)
        if gen is None:
            return
        gen.end(
            output=response.content,
            usage={
                "input": response.usage.get("prompt_tokens", 0),
                "output": response.usage.get("completion_tokens", 0),
            },
            metadata={
                "latency_ms": latency_ms,
                "tool_calls": [tc.name for tc in (response.tool_calls or [])],
                "finish_reason": response.finish_reason,
                "provider": response.provider,
            },
            level="ERROR" if response.error else "DEFAULT",
        )

    async def on_error(self, exc: Exception, request) -> None:
        gen = self._pending.pop(request.request_id, None)
        if gen is not None:
            gen.end(level="ERROR", status_message=str(exc))

    def flush(self) -> None:
        self._client.flush()

    def _evict_overflow(self) -> None:
        if len(self._pending) > 1000:
            logger.warning(
                "LangFuseObserver: _pending overflow (%d entries) — evicting oldest",
                len(self._pending),
            )
            oldest_key = next(iter(self._pending))
            self._pending.pop(oldest_key, None)
