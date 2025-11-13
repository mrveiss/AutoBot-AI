"""
LLM Stream Processor - Natural Completion Detection for Streaming
Eliminates complex timeout logic and uses natural stream completion detection
Intelligent streaming with simplified error handling
"""

import asyncio
import json
import logging
import time
from typing import Tuple

import aiohttp

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class LLMStreamProcessor:
    """
    LLM streaming processor that eliminates complex timeout logic
    and uses natural stream completion detection
    """

    def __init__(self, response: aiohttp.ClientResponse):
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
            logger.error(f"Stream processing error: {e}")
            return "".join(self.content_buffer), False

    def get_processing_time(self) -> float:
        """Get processing time in milliseconds"""
        return (time.time() - self.start_time) * 1000


class LLMStreamingInterface:
    """
    LLM streaming interface with simplified streaming and better error handling
    """

    def __init__(self):
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self.session is None or self.session.closed:
            # Connection pooling settings for better performance
            connector = aiohttp.TCPConnector(
                limit=100,  # Connection pool size
                limit_per_host=10,  # Max connections per host
                keepalive_timeout=30,  # Keep connections alive
                enable_cleanup_closed=True,
            )

            timeout = aiohttp.ClientTimeout(total=None)  # No overall timeout

            self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)

        return self.session

    async def stream_ollama_request(self, url: str, data: dict) -> Tuple[str, bool]:
        """
        Make streaming request to Ollama with natural completion detection
        Returns: (response_content, success)
        """
        session = await self._get_session()

        try:
            async with session.post(url, json=data) as response:
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
            logger.error(f"Ollama request exception: {e}")
            return f"Error: {str(e)}", False

    async def cleanup(self):
        """Clean up HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()


# Global LLM streaming interface instance
_llm_streaming_interface = None


async def get_llm_streaming_interface() -> LLMStreamingInterface:
    """Get global LLM streaming interface instance"""
    global _llm_streaming_interface
    if _llm_streaming_interface is None:
        _llm_streaming_interface = LLMStreamingInterface()
    return _llm_streaming_interface
