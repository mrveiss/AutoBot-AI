# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Stream Processor - Natural Completion Detection for Streaming
Eliminates complex timeout logic and uses natural stream completion detection
Intelligent streaming with simplified error handling
"""

import json
import logging
import time
from typing import Tuple

import aiohttp

from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)


class LLMStreamProcessor:
    """
    LLM streaming processor that eliminates complex timeout logic
    and uses natural stream completion detection
    """

    def __init__(self, response: aiohttp.ClientResponse):
        """Initialize stream processor with response object and timing state."""
        self.response = response
        self.start_time = time.time()
        self.content_buffer = []
        self.chunk_count = 0

    async def process_ollama_stream(self) -> Tuple[str, bool]:
        """
        Process Ollama stream with natural completion detection
        Returns: (accumulated_content, completed_successfully)
        """
        try:
            async for line in self.response.content:
                line = line.decode("utf-8").strip()
                if not line:
                    continue

                try:
                    chunk_data = json.loads(line)

                    # Extract message content
                    if "message" in chunk_data and "content" in chunk_data["message"]:
                        content = chunk_data["message"]["content"]
                        self.content_buffer.append(content)

                    # Natural completion detection - Ollama sends "done": true
                    if chunk_data.get("done", False):
                        return "".join(self.content_buffer), True

                    self.chunk_count += 1

                    # Safety limit to prevent infinite loops
                    if self.chunk_count > 5000:  # Increased limit
                        logger.warning("Stream exceeded chunk limit, completing")
                        return "".join(self.content_buffer), False

                except json.JSONDecodeError:
                    continue  # Skip malformed chunks

            # Stream ended naturally without "done" signal
            return "".join(self.content_buffer), True

        except Exception as e:
            logger.error("Stream processing error: %s", e)
            return "".join(self.content_buffer), False

    def get_processing_time(self) -> float:
        """Get processing time in milliseconds"""
        return (time.time() - self.start_time) * 1000


class LLMStreamingInterface:
    """
    LLM streaming interface with simplified streaming and better error handling
    """

    def __init__(self):
        """Initialize streaming interface with singleton HTTP client."""
        self._http_client = get_http_client()  # Use singleton HTTP client

    async def stream_ollama_request(self, url: str, data: dict) -> Tuple[str, bool]:
        """
        Make streaming request to Ollama with natural completion detection
        Returns: (response_content, success)
        """
        try:
            async with await self._http_client.post(url, json=data) as response:
                if response.status == 200:
                    processor = LLMStreamProcessor(response)
                    content, success = await processor.process_ollama_stream()

                    processing_time = processor.get_processing_time()
                    logger.info(
                        f"Stream processed in {processing_time:.2f}ms with {processor.chunk_count} chunks"
                    )

                    return content, success
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Ollama request failed: {response.status} - {error_text}"
                    )
                    return f"Error: HTTP {response.status}", False

        except Exception as e:
            logger.error("Ollama request exception: %s", e)
            return f"Error: {str(e)}", False

    async def cleanup(self):
        """No-op: HTTP session is managed by singleton HTTPClientManager"""


# Global LLM streaming interface instance (thread-safe)
import asyncio as _asyncio_lock

_llm_streaming_interface = None
_llm_streaming_interface_lock = _asyncio_lock.Lock()


async def get_llm_streaming_interface() -> LLMStreamingInterface:
    """Get global LLM streaming interface instance (thread-safe)"""
    global _llm_streaming_interface
    if _llm_streaming_interface is None:
        async with _llm_streaming_interface_lock:
            # Double-check after acquiring lock
            if _llm_streaming_interface is None:
                _llm_streaming_interface = LLMStreamingInterface()
    return _llm_streaming_interface
