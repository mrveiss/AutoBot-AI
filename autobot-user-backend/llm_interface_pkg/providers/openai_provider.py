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

from circuit_breaker import circuit_breaker_async
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

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
            api_key: OpenAI API key (falls back to unified config #536)
        """
        if api_key:
            self.api_key = api_key
        else:
            from config import UnifiedConfigManager

            self.api_key = UnifiedConfigManager().get_api_key("openai")

    def _record_success_span_attributes(
        self, span, response, processing_time: float
    ) -> None:
        """
        Record success attributes on OpenTelemetry span. Issue #620.

        Args:
            span: OpenTelemetry span
            response: OpenAI API response
            processing_time: Time taken to process request
        """
        if span.is_recording():
            span.set_attribute("llm.duration_ms", processing_time * 1000)
            span.set_attribute(
                "llm.response_length", len(response.choices[0].message.content)
            )
            span.set_attribute("llm.prompt_tokens", response.usage.prompt_tokens)
            span.set_attribute(
                "llm.completion_tokens", response.usage.completion_tokens
            )
            span.set_attribute("llm.total_tokens", response.usage.total_tokens)
            span.set_status(Status(StatusCode.OK))

    def _build_response(
        self, response, processing_time: float, request_id: str
    ) -> LLMResponse:
        """
        Build LLMResponse from OpenAI API response. Issue #620.

        Args:
            response: OpenAI API response
            processing_time: Time taken to process request
            request_id: Request identifier

        Returns:
            LLMResponse object
        """
        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            provider="openai",
            processing_time=processing_time,
            request_id=request_id,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        )

    def _build_span_attributes(self, model: str, request: LLMRequest) -> dict:
        """
        Build span attributes for OpenTelemetry tracing. Issue #620.

        Args:
            model: Model name
            request: LLM request object

        Returns:
            Dict of span attributes
        """
        return {
            "llm.provider": "openai",
            "llm.model": model,
            "llm.request_id": request.request_id,
            "llm.temperature": request.temperature,
            "llm.max_tokens": request.max_tokens or 0,
            "llm.prompt_messages": len(request.messages),
        }

    def _record_error_span_attributes(self, span, error: Exception) -> None:
        """
        Record error attributes on OpenTelemetry span. Issue #620.

        Args:
            span: OpenTelemetry span
            error: Exception that occurred
        """
        if span.is_recording():
            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.record_exception(error)
            span.set_attribute("llm.error", True)

    async def _execute_openai_request(self, client, model: str, request: LLMRequest):
        """Execute the OpenAI API request. Issue #620."""
        return await client.chat.completions.create(
            model=model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

    @circuit_breaker_async("openai_service")
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Enhanced OpenAI chat completion. Issue #620."""
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")

        import openai

        client = openai.AsyncOpenAI(api_key=self.api_key)
        model = request.model_name or "gpt-3.5-turbo"
        span_attrs = self._build_span_attributes(model, request)

        with _tracer.start_as_current_span(
            "llm.inference", kind=SpanKind.CLIENT, attributes=span_attrs
        ) as span:
            start_time = time.time()
            try:
                response = await self._execute_openai_request(client, model, request)
                processing_time = time.time() - start_time
                self._record_success_span_attributes(span, response, processing_time)
                return self._build_response(
                    response, processing_time, request.request_id
                )
            except Exception as e:
                logger.error("OpenAI completion error: %s", e)
                self._record_error_span_attributes(span, e)
                raise


__all__ = [
    "OpenAIProvider",
]
