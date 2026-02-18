# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ollama Provider - Handler for Ollama LLM requests with streaming support.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
Issue #551: Added proper async cancellation handling and timeout fixes.
Issue #697: Added OpenTelemetry tracing spans for LLM inference.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import aiohttp
from circuit_breaker import circuit_breaker_async
from config import UnifiedConfigManager
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from autobot_shared.http_client import get_http_client
from autobot_shared.ssot_config import get_ollama_url

from ..models import LLMRequest, LLMResponse, LLMSettings
from ..streaming import StreamingManager

logger = logging.getLogger(__name__)
config = UnifiedConfigManager()

# Issue #697: Get tracer for LLM operations
_tracer = trace.get_tracer("autobot.llm.ollama", "2.0.0")


class OllamaProvider:
    """
    Ollama LLM Provider with streaming support and circuit breaker protection.

    Handles all Ollama-specific request formatting, streaming, and response parsing.
    """

    def __init__(
        self,
        settings: LLMSettings,
        streaming_manager: StreamingManager,
    ):
        """
        Initialize Ollama provider.

        Args:
            settings: LLM configuration settings
            streaming_manager: Manager for streaming state
        """
        self.settings = settings
        self.streaming_manager = streaming_manager
        self._http_client = get_http_client()
        self.ollama_host: Optional[str] = None

    @asynccontextmanager
    async def _get_session(self) -> AsyncGenerator[aiohttp.ClientSession, None]:
        """Get HTTP session using singleton HTTPClient."""
        session = await self._http_client.get_session()
        yield session

    def get_host_from_env(self) -> str:
        """
        Get Ollama host URL from SSOT config (same path as individual agents).

        Returns:
            Ollama host URL
        """
        host_url = get_ollama_url()
        logger.debug("[REQUEST] Using Ollama URL from config: %s", host_url)
        return host_url

    def build_request_data(
        self, request: LLMRequest, model: str, use_streaming: bool
    ) -> dict:
        """
        Build Ollama API request data dictionary.

        Args:
            request: LLM request object
            model: Model name to use
            use_streaming: Whether to enable streaming

        Returns:
            Request data dictionary
        """
        return {
            "model": model,
            "messages": request.messages,
            "stream": use_streaming,
            "temperature": request.temperature,
            "format": "json" if request.structured_output else "",
            "options": {
                "seed": 42,
                "top_k": self.settings.top_k,
                "top_p": self.settings.top_p,
                "repeat_penalty": self.settings.repeat_penalty,
                "num_ctx": self.settings.num_ctx,
            },
        }

    def extract_content(self, response: dict) -> str:
        """
        Safely extract content from Ollama response.

        Args:
            response: Response dictionary from Ollama

        Returns:
            Extracted content string
        """
        if "message" in response and isinstance(response["message"], dict):
            return response["message"].get("content", "")
        elif "response" in response:  # Alternative Ollama format
            return response.get("response", "")
        else:
            logger.warning("Unexpected response structure: %s", response)
            return str(response)

    def build_response(
        self,
        content: str,
        response: dict,
        model: str,
        processing_time: float,
        request_id: str,
        fallback_used: bool = False,
    ) -> LLMResponse:
        """
        Build LLMResponse from extracted content.

        Args:
            content: Extracted content string
            response: Original response dictionary
            model: Model name
            processing_time: Time taken to process
            request_id: Request identifier
            fallback_used: Whether fallback was used

        Returns:
            LLMResponse object
        """
        return LLMResponse(
            content=content,
            model=response.get("model", model),
            provider="ollama",
            processing_time=processing_time,
            request_id=request_id,
            metadata=response.get("stats", {}),
            usage=response.get("usage", {}),
            fallback_used=fallback_used,
        )

    def build_error_response(self, model: str, error: Exception) -> dict:
        """
        Build error response dict for streaming failures.

        Args:
            model: Model name
            error: Exception that occurred

        Returns:
            Error response dictionary
        """
        return {
            "message": {
                "role": "assistant",
                "content": f"Streaming error occurred: {str(error)}",
            },
            "model": model,
            "error": str(error),
        }

    def _record_success_span_attributes(
        self, span, processing_time: float, content: str
    ) -> None:
        """
        Record success attributes on OpenTelemetry span. Issue #620.

        Args:
            span: OpenTelemetry span
            processing_time: Time taken to process request
            content: Response content
        """
        if span.is_recording():
            span.set_attribute("llm.duration_ms", processing_time * 1000)
            span.set_attribute("llm.response_length", len(content))
            span.set_status(Status(StatusCode.OK))

    def _build_span_attributes(
        self, model: str, use_streaming: bool, request: LLMRequest
    ) -> dict:
        """
        Build span attributes for OpenTelemetry tracing. Issue #620.

        Args:
            model: Model name
            use_streaming: Whether streaming is enabled
            request: LLM request object

        Returns:
            Dict of span attributes
        """
        return {
            "llm.provider": "ollama",
            "llm.model": model,
            "llm.streaming": use_streaming,
            "llm.request_id": request.request_id,
            "llm.temperature": request.temperature,
            "llm.prompt_messages": len(request.messages),
        }

    async def _execute_request(
        self,
        url: str,
        headers: dict,
        data: dict,
        request_id: str,
        model: str,
        use_streaming: bool,
    ) -> dict:
        """
        Execute LLM request and validate response type. Issue #620.

        Args:
            url: API URL
            headers: Request headers
            data: Request data
            request_id: Request identifier
            model: Model name
            use_streaming: Whether streaming is enabled

        Returns:
            Response dictionary
        """
        if use_streaming:
            response = await self.stream_response(url, headers, data, request_id, model)
            self.streaming_manager.record_success(model)
        else:
            response = await self.non_streaming_request(url, headers, data, request_id)

        if not isinstance(response, dict):
            logger.error(
                f"Streaming response is not a dict: {type(response)} - {response}"
            )
            response = {"message": {"content": str(response)}, "model": model}

        return response

    def _handle_streaming_error(
        self,
        span,
        model: str,
        start_time: float,
        request_id: str,
        error: Exception,
    ) -> LLMResponse:
        """
        Handle streaming failure and build error response. Issue #620.

        Args:
            span: OpenTelemetry span
            model: Model name
            start_time: Request start time
            request_id: Request identifier
            error: Exception that occurred

        Returns:
            LLMResponse with error information
        """
        self.streaming_manager.record_failure(model)
        logger.error("Streaming REQUIRED but failed for %s: %s", model, error)
        processing_time = time.time() - start_time

        response = self.build_error_response(model, error)
        content = self.extract_content(response)

        if span.is_recording():
            span.set_attribute("llm.fallback_used", True)

        return self.build_response(
            content,
            response,
            model,
            processing_time,
            request_id,
            fallback_used=True,
        )

    def _create_streaming_timeout(self) -> aiohttp.ClientTimeout:
        """
        Issue #665: Extracted from stream_response to reduce function length.

        Create timeout configuration for streaming requests.
        Issue #551: sock_read=None allows streaming to complete naturally.

        Returns:
            aiohttp.ClientTimeout configured for streaming
        """
        return aiohttp.ClientTimeout(
            total=None,  # No total timeout for streaming
            connect=5.0,  # Quick connection timeout
            sock_read=None,  # CRITICAL: Let streaming complete naturally
            sock_connect=5.0,
        )

    async def _process_stream_response(
        self, response: aiohttp.ClientResponse, request_id: str
    ) -> dict:
        """
        Issue #665: Extracted from stream_response to reduce function length.

        Process the streaming response and return accumulated content.

        Args:
            response: aiohttp response object
            request_id: Request identifier

        Returns:
            Response dictionary with accumulated content
        """
        from utils.async_stream_processor import process_llm_stream

        accumulated_content, completed_successfully = await process_llm_stream(
            response,
            provider="ollama",
            max_chunks=self.settings.max_chunks,
            max_buffer_size=10 * 1024 * 1024,  # 10MB protection
        )

        if not completed_successfully:
            logger.warning(f"[{request_id}] Stream did not complete properly")

        logger.info(
            f"[{request_id}] Stream processing completed: "
            f"{len(accumulated_content)} chars"
        )

        return {
            "message": {"role": "assistant", "content": accumulated_content},
            "done": True,
            "completed_successfully": completed_successfully,
        }

    async def stream_response(
        self,
        url: str,
        headers: dict,
        data: dict,
        request_id: str,
        model: str,
    ) -> dict:
        """
        Stream Ollama response with comprehensive timeout protection.

        Issue #551: Fixed from archived llm_interface_fixed.py
        Issue #665: Refactored to use helper methods for reduced complexity.

        Args:
            url: Ollama API URL
            headers: Request headers
            data: Request data
            request_id: Request identifier
            model: Model name

        Returns:
            Response dictionary with accumulated content
        """
        start_time = time.time()
        logger.info("[%s] Starting protected streaming for model %s", request_id, model)

        try:
            async with self._get_session() as session:
                timeout = self._create_streaming_timeout()
                async with session.post(
                    url, headers=headers, json=data, timeout=timeout
                ) as response:
                    if response.status != 200:
                        raise aiohttp.ClientError(
                            f"HTTP {response.status}: {await response.text()}"
                        )
                    return await self._process_stream_response(response, request_id)
        except asyncio.CancelledError:
            duration = time.time() - start_time
            logger.info(
                "[%s] Stream cancelled by user after %.2fs", request_id, duration
            )
            raise
        except Exception as e:
            duration = time.time() - start_time
            logger.error("[%s] Stream error after %.2fs: %s", request_id, duration, e)
            raise

    async def non_streaming_request(
        self,
        url: str,
        headers: dict,
        data: dict,
        request_id: str,
    ) -> dict:
        """
        Non-streaming Ollama request as fallback.

        Args:
            url: Ollama API URL
            headers: Request headers
            data: Request data
            request_id: Request identifier

        Returns:
            Response dictionary
        """
        data_copy = data.copy()
        data_copy["stream"] = False

        logger.info("[%s] Using non-streaming request", request_id)

        async with self._get_session() as session:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with session.post(
                url, headers=headers, json=data_copy, timeout=timeout
            ) as response:
                if response.status != 200:
                    raise aiohttp.ClientError(
                        f"HTTP {response.status}: {await response.text()}"
                    )

                result = await response.json()
                return result

    def _prepare_chat_request(self, request: LLMRequest) -> tuple:
        """
        Prepare chat completion request parameters. Issue #620.

        Args:
            request: LLM request object

        Returns:
            Tuple of (url, headers, model, use_streaming, data, span_attrs)
        """
        self.ollama_host = self.get_host_from_env()
        url = f"{self.ollama_host}/api/chat"
        headers = {"Content-Type": "application/json"}

        model = request.model_name or self.settings.default_model
        use_streaming = self.streaming_manager.should_use_streaming(model)
        data = self.build_request_data(request, model, use_streaming)
        span_attrs = self._build_span_attributes(model, use_streaming, request)

        return url, headers, model, use_streaming, data, span_attrs

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

    @circuit_breaker_async(
        "ollama_service",
        failure_threshold=config.get("circuit_breaker.ollama.failure_threshold", 3),
        recovery_timeout=config.get_timeout("circuit_breaker", "recovery"),
        timeout=config.get_timeout("llm", "default"),
    )
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Enhanced Ollama chat completion with improved streaming.

        Issue #697: Added OpenTelemetry tracing for LLM inference monitoring.
        Issue #620: Refactored to use helper methods for reduced complexity.

        Args:
            request: LLM request object

        Returns:
            LLMResponse object
        """
        (
            url,
            headers,
            model,
            use_streaming,
            data,
            span_attrs,
        ) = self._prepare_chat_request(request)

        with _tracer.start_as_current_span(
            "llm.inference", kind=SpanKind.CLIENT, attributes=span_attrs
        ) as span:
            start_time = time.time()

            try:
                response = await self._execute_request(
                    url, headers, data, request.request_id, model, use_streaming
                )
                processing_time = time.time() - start_time
                content = self.extract_content(response)
                self._record_success_span_attributes(span, processing_time, content)

                return self.build_response(
                    content, response, model, processing_time, request.request_id
                )

            except Exception as e:
                self._record_error_span_attributes(span, e)
                if use_streaming:
                    return self._handle_streaming_error(
                        span, model, start_time, request.request_id, e
                    )
                raise e


__all__ = [
    "OllamaProvider",
]
