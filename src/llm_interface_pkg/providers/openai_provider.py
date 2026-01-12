# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OpenAI Provider - Handler for OpenAI LLM requests.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
Issue #697: Added OpenTelemetry tracing spans for LLM inference.
"""

import logging
import time
from typing import Optional

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from src.circuit_breaker import circuit_breaker_async

from ..models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

# Issue #697: Get tracer for LLM operations
_tracer = trace.get_tracer("autobot.llm.openai", "2.0.0")


class OpenAIProvider:
    """
    OpenAI LLM Provider with circuit breaker protection.

    Handles all OpenAI-specific request formatting and response parsing.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
        """
        self.api_key = api_key

    @circuit_breaker_async("openai_service")
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Enhanced OpenAI chat completion.

        Issue #697: Added OpenTelemetry tracing for LLM inference monitoring.

        Args:
            request: LLM request object

        Returns:
            LLMResponse object

        Raises:
            ValueError: If API key is not configured
        """
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")

        import openai

        client = openai.AsyncOpenAI(api_key=self.api_key)
        model = request.model_name or "gpt-3.5-turbo"

        # Issue #697: Create span for LLM inference with model attributes
        with _tracer.start_as_current_span(
            "llm.inference",
            kind=SpanKind.CLIENT,
            attributes={
                "llm.provider": "openai",
                "llm.model": model,
                "llm.request_id": request.request_id,
                "llm.temperature": request.temperature,
                "llm.max_tokens": request.max_tokens or 0,
                "llm.prompt_messages": len(request.messages),
            },
        ) as span:
            start_time = time.time()

            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )

                processing_time = time.time() - start_time

                # Issue #697: Record response attributes on span
                if span.is_recording():
                    span.set_attribute("llm.duration_ms", processing_time * 1000)
                    span.set_attribute(
                        "llm.response_length", len(response.choices[0].message.content)
                    )
                    span.set_attribute(
                        "llm.prompt_tokens", response.usage.prompt_tokens
                    )
                    span.set_attribute(
                        "llm.completion_tokens", response.usage.completion_tokens
                    )
                    span.set_attribute("llm.total_tokens", response.usage.total_tokens)
                    span.set_status(Status(StatusCode.OK))

                return LLMResponse(
                    content=response.choices[0].message.content,
                    model=response.model,
                    provider="openai",
                    processing_time=processing_time,
                    request_id=request.request_id,
                    usage={
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    },
                )

            except Exception as e:
                processing_time = time.time() - start_time
                logger.error("OpenAI completion error: %s", e)

                # Issue #697: Record error on span
                if span.is_recording():
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    span.set_attribute("llm.error", True)

                raise


__all__ = [
    "OpenAIProvider",
]
