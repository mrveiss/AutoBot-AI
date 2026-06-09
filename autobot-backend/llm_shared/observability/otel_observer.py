# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
OTELObserver — centralised OpenTelemetry span emission for LLM inference (GH#6593).

Replaces the per-provider _tracer instances previously copy-pasted into
openai.py, anthropic.py, ollama.py, nous_portal.py, and openrouter.py.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_tracer = trace.get_tracer("autobot.llm", "2.0.0")


class OTELObserver:
    """Emit an OpenTelemetry span for every completed or failed LLM call."""

    async def on_request(self, request, metadata: dict) -> None:
        pass

    async def on_response(self, response, latency_ms: float, cost: float) -> None:
        span_attrs = {
            "llm.provider": response.provider or "",
            "llm.model": response.model or "",
            "llm.request_id": response.request_id or "",
            "llm.duration_ms": latency_ms,
            "llm.response_length": len(response.content or ""),
            "llm.prompt_tokens": (response.usage or {}).get("prompt_tokens", 0),
            "llm.completion_tokens": (response.usage or {}).get("completion_tokens", 0),
            "llm.total_tokens": (response.usage or {}).get("total_tokens", 0),
        }
        with _tracer.start_as_current_span("llm.inference", kind=SpanKind.CLIENT, attributes=span_attrs) as span:
            if response.error:
                span.set_status(Status(StatusCode.ERROR, response.error))
                span.set_attribute("llm.error", True)
            else:
                span.set_status(Status(StatusCode.OK))

    async def on_error(self, exc: Exception, request) -> None:
        span_attrs = {
            "llm.provider": str(getattr(request, "provider", "") or ""),
            "llm.model": request.model_name or "",
            "llm.request_id": request.request_id or "",
            "llm.error": True,
        }
        with _tracer.start_as_current_span("llm.inference.error", kind=SpanKind.CLIENT, attributes=span_attrs) as span:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
