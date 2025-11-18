# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Async Stream Processor - Replaces timeout-based streaming with completion detection
Handles LLM streaming responses using natural completion signals instead of timeouts
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class StreamCompletionSignal(Enum):
    """Signals that indicate stream completion"""

    DONE_CHUNK_RECEIVED = "done_chunk_received"
    JSON_COMPLETION = "json_completion"
    PROVIDER_SPECIFIC = "provider_specific"
    CONNECTION_CLOSED = "connection_closed"
    ERROR_CONDITION = "error_condition"
    MAX_CHUNKS_REACHED = "max_chunks_reached"


@dataclass
class StreamProcessingResult:
    """Result of stream processing"""

    content: str
    completed_successfully: bool
    completion_signal: StreamCompletionSignal
    total_chunks: int
    processing_time: float
    metadata: Dict[str, Any]
    error_message: Optional[str] = None


class StreamProcessor:
    """Base stream processor for different LLM providers"""

    def __init__(self, provider: str, max_chunks: int = 1000):
        self.provider = provider
        self.max_chunks = max_chunks
        self.chunk_count = 0
        self.accumulated_content = ""
        self.start_time = None

    async def process_chunk(self, chunk_data: str) -> Tuple[bool, Optional[str]]:
        """
        Process a single chunk. Returns (is_complete, content_to_add)
        Must be implemented by provider-specific processors
        """
        raise NotImplementedError

    def is_natural_completion(self, chunk_data: str, content_so_far: str) -> bool:
        """Check if chunk indicates natural completion"""
        return False

    def detect_error_condition(self, chunk_data: str) -> Optional[str]:
        """Detect error conditions in chunk"""
        return None


class OllamaStreamProcessor(StreamProcessor):
    """Ollama-specific stream processor"""

    def __init__(self, max_chunks: int = 1000):
        super().__init__("ollama", max_chunks)
        self.expecting_done = False

    async def process_chunk(self, chunk_data: str) -> Tuple[bool, Optional[str]]:
        """Process Ollama streaming chunk"""
        if not chunk_data.strip():
            return False, None

        try:
            # Parse JSON chunk
            chunk_json = json.loads(chunk_data.strip())

            # Check for error in chunk
            if "error" in chunk_json:
                error_msg = chunk_json.get("error", "Unknown error")
                logger.error(f"Ollama streaming error: {error_msg}")
                return True, None  # Complete with error

            # Check for completion signal
            if chunk_json.get("done", False):
                logger.info(f"🎯 Ollama stream completion signal received (done=true)")
                self.expecting_done = True
                return True, None  # Natural completion

            # Extract content from message
            message = chunk_json.get("message", {})
            content = message.get("content", "")

            if content:
                return False, content

            # Check for response field (alternative format)
            if "response" in chunk_json:
                response_content = chunk_json["response"]
                if response_content:
                    return False, response_content

            return False, None

        except json.JSONDecodeError as e:
            logger.warning(
                f"Invalid JSON chunk from Ollama: {chunk_data[:100]}... Error: {e}"
            )
            # Try to extract any plain text content
            if chunk_data.strip():
                return False, chunk_data.strip()
            return False, None

    def is_natural_completion(self, chunk_data: str, content_so_far: str) -> bool:
        """Check for natural completion indicators"""
        try:
            chunk_json = json.loads(chunk_data.strip())

            # Primary completion signal
            if chunk_json.get("done", False):
                return True

            # Secondary completion indicators
            if chunk_json.get("eval_count") and chunk_json.get("eval_duration"):
                return True  # Statistics usually indicate completion

            return False

        except json.JSONDecodeError:
            return False

    def detect_error_condition(self, chunk_data: str) -> Optional[str]:
        """Detect Ollama error conditions"""
        try:
            chunk_json = json.loads(chunk_data.strip())
            return chunk_json.get("error")
        except json.JSONDecodeError:
            return None


class OpenAIStreamProcessor(StreamProcessor):
    """OpenAI-specific stream processor"""

    def __init__(self, max_chunks: int = 1000):
        super().__init__("openai", max_chunks)

    async def process_chunk(self, chunk_data: str) -> Tuple[bool, Optional[str]]:
        """Process OpenAI streaming chunk"""
        if not chunk_data.strip():
            return False, None

        # OpenAI uses SSE format
        if chunk_data.startswith("data: "):
            data_content = chunk_data[6:].strip()

            # Check for completion signal
            if data_content == "[DONE]":
                logger.info("🎯 OpenAI stream completion signal received ([DONE])")
                return True, None

            try:
                chunk_json = json.loads(data_content)

                # Extract content from delta
                choices = chunk_json.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")

                    # Check for finish_reason
                    if choices[0].get("finish_reason"):
                        logger.info(
                            f"🎯 OpenAI completion: {choices[0]['finish_reason']}"
                        )
                        return True, content if content else None

                    return False, content if content else None

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in OpenAI chunk: {data_content}")

        return False, None


class StreamProcessorFactory:
    """Factory for creating provider-specific processors"""

    @staticmethod
    def create_processor(provider: str, max_chunks: int = 1000) -> StreamProcessor:
        """Create appropriate processor for provider"""
        provider_lower = provider.lower()

        if provider_lower == "ollama":
            return OllamaStreamProcessor(max_chunks)
        elif provider_lower in ["openai", "gpt"]:
            return OpenAIStreamProcessor(max_chunks)
        else:
            # Generic processor for unknown providers
            return StreamProcessor(provider, max_chunks)


async def process_llm_stream(
    response, provider: str = "ollama", max_chunks: int = 1000
) -> Tuple[str, bool]:
    """
    Process LLM streaming response using completion signals instead of timeouts.

    Args:
        response: HTTP response object with streaming content
        provider: LLM provider name
        max_chunks: Maximum chunks to process (safety limit)

    Returns:
        Tuple of (accumulated_content, completed_successfully)
    """

    processor = StreamProcessorFactory.create_processor(provider, max_chunks)
    processor.start_time = asyncio.get_event_loop().time()

    accumulated_content = ""
    chunk_count = 0
    completion_signal = None
    error_message = None

    logger.info(f"🔄 Starting {provider} stream processing (max_chunks: {max_chunks})")

    try:
        async for chunk_bytes in response.content:
            chunk_count += 1

            # Safety limit to prevent infinite loops
            if chunk_count > max_chunks:
                logger.warning(f"⚠️ Reached maximum chunk limit ({max_chunks})")
                completion_signal = StreamCompletionSignal.MAX_CHUNKS_REACHED
                break

            # Decode chunk
            try:
                chunk_data = chunk_bytes.decode("utf-8")
            except UnicodeDecodeError as e:
                logger.warning(f"Unicode decode error in chunk {chunk_count}: {e}")
                continue

            if not chunk_data.strip():
                continue

            # Check for error conditions
            error = processor.detect_error_condition(chunk_data)
            if error:
                error_message = error
                completion_signal = StreamCompletionSignal.ERROR_CONDITION
                logger.error(f"❌ Stream error detected: {error}")
                break

            # Process chunk through provider-specific processor
            is_complete, content_to_add = await processor.process_chunk(chunk_data)

            # Add content if available
            if content_to_add:
                accumulated_content += content_to_add

            # Check for completion
            if is_complete:
                if processor.is_natural_completion(chunk_data, accumulated_content):
                    completion_signal = StreamCompletionSignal.DONE_CHUNK_RECEIVED
                    logger.info(
                        f"✅ Stream completed naturally after {chunk_count} chunks"
                    )
                else:
                    completion_signal = StreamCompletionSignal.PROVIDER_SPECIFIC
                    logger.info(
                        f"✅ Stream completed (provider signal) after {chunk_count} chunks"
                    )
                break

            # Brief yield to prevent blocking
            if chunk_count % 10 == 0:  # Every 10 chunks
                await asyncio.sleep(0)

    except Exception as e:
        error_message = str(e)
        completion_signal = StreamCompletionSignal.ERROR_CONDITION
        logger.error(f"❌ Stream processing error: {e}")

    # Final processing
    processing_time = asyncio.get_event_loop().time() - processor.start_time
    completed_successfully = completion_signal in [
        StreamCompletionSignal.DONE_CHUNK_RECEIVED,
        StreamCompletionSignal.JSON_COMPLETION,
        StreamCompletionSignal.PROVIDER_SPECIFIC,
    ]

    logger.info(
        f"🏁 Stream processing complete: "
        f"chunks={chunk_count}, "
        f"content_length={len(accumulated_content)}, "
        f"success={completed_successfully}, "
        f"signal={completion_signal}, "
        f"time={processing_time:.2f}s"
    )

    return accumulated_content, completed_successfully


async def process_stream_with_cancellation(
    response, cancellation_token, provider: str = "ollama", max_chunks: int = 1000
) -> StreamProcessingResult:
    """
    Process stream with cancellation support.
    Combines natural completion detection with cancellation tokens.
    """

    start_time = asyncio.get_event_loop().time()

    try:
        # Check cancellation before starting
        if hasattr(cancellation_token, "raise_if_cancelled"):
            cancellation_token.raise_if_cancelled()

        # Process stream
        content, success = await process_llm_stream(response, provider, max_chunks)

        # Check cancellation after completion
        if hasattr(cancellation_token, "raise_if_cancelled"):
            cancellation_token.raise_if_cancelled()

        processing_time = asyncio.get_event_loop().time() - start_time

        return StreamProcessingResult(
            content=content,
            completed_successfully=success,
            completion_signal=(
                StreamCompletionSignal.DONE_CHUNK_RECEIVED
                if success
                else StreamCompletionSignal.ERROR_CONDITION
            ),
            total_chunks=0,  # Will be filled by processor
            processing_time=processing_time,
            metadata={"provider": provider, "max_chunks": max_chunks},
        )

    except Exception as e:
        processing_time = asyncio.get_event_loop().time() - start_time

        return StreamProcessingResult(
            content="",
            completed_successfully=False,
            completion_signal=StreamCompletionSignal.ERROR_CONDITION,
            total_chunks=0,
            processing_time=processing_time,
            metadata={"provider": provider, "error": str(e)},
            error_message=str(e),
        )
