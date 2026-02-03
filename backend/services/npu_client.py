# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Worker Client Service

Issue #640: Provides a unified client for offloading compute to the NPU worker.
When NPU worker is available, embedding generation and other compute tasks
are offloaded to NPU/GPU for acceleration. Falls back to Ollama if unavailable.

Usage:
    from backend.services.npu_client import get_npu_client, NPUClient

    client = get_npu_client()
    if await client.is_available():
        embeddings = await client.generate_embeddings(texts)
"""

import asyncio
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp

from src.config.ssot_config import get_config

logger = logging.getLogger(__name__)

# Configuration from SSOT with environment override capability
_ssot = get_config()
NPU_WORKER_HOST = os.getenv("AUTOBOT_NPU_WORKER_HOST", _ssot.vm.npu)
NPU_WORKER_PORT = os.getenv("AUTOBOT_NPU_WORKER_PORT", str(_ssot.port.npu))
NPU_WORKER_URL = f"http://{NPU_WORKER_HOST}:{NPU_WORKER_PORT}"

# Timeouts
HEALTH_CHECK_TIMEOUT = 2.0
EMBEDDING_TIMEOUT = 30.0
BATCH_TIMEOUT = 60.0

# Cache for health status
HEALTH_CHECK_CACHE_TTL = 30  # seconds


@dataclass
class NPUDeviceInfo:
    """Information about the NPU worker device"""
    selected_device: str
    available_devices: List[str]
    is_npu: bool
    is_gpu: bool
    is_cpu: bool
    real_inference: bool
    device_name: str = ""


@dataclass
class EmbeddingResult:
    """Result of embedding generation"""
    embeddings: List[List[float]]
    model_used: str
    processing_time_ms: float
    device: str
    real_inference: bool
    texts_processed: int
    from_npu_worker: bool = True


class NPUClient:
    """
    Client for offloading compute to NPU Worker.

    Provides embedding generation with automatic fallback to Ollama
    when NPU worker is unavailable.
    """

    def __init__(self, base_url: str = NPU_WORKER_URL):
        self.base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._is_available: Optional[bool] = None
        self._last_health_check: float = 0
        self._device_info: Optional[NPUDeviceInfo] = None
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=EMBEDDING_TIMEOUT)
            )
        return self._session

    async def close(self):
        """Close the client session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def is_available(self, force_check: bool = False) -> bool:
        """
        Check if NPU worker is available.

        Uses cached result unless force_check=True or cache expired.
        """
        import time

        current_time = time.time()

        # Return cached result if valid
        if not force_check and self._is_available is not None:
            if current_time - self._last_health_check < HEALTH_CHECK_CACHE_TTL:
                return self._is_available

        # Perform health check
        async with self._lock:
            try:
                session = await self._get_session()
                async with session.get(
                    f"{self.base_url}/health",
                    timeout=aiohttp.ClientTimeout(total=HEALTH_CHECK_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._is_available = data.get("status") == "healthy"
                        self._last_health_check = current_time
                        logger.info(f"NPU worker available: {self._is_available}")
                        return self._is_available
            except Exception as e:
                logger.debug(f"NPU worker not available: {e}")

            self._is_available = False
            self._last_health_check = current_time
            return False

    async def get_device_info(self) -> Optional[NPUDeviceInfo]:
        """Get information about the NPU worker's device"""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/device-info",
                timeout=aiohttp.ClientTimeout(total=HEALTH_CHECK_TIMEOUT)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    manager = data.get("model_manager", {})

                    self._device_info = NPUDeviceInfo(
                        selected_device=data.get("selected_device", "UNKNOWN"),
                        available_devices=data.get("available_devices", []),
                        is_npu=manager.get("is_npu", False),
                        is_gpu=manager.get("is_gpu", False),
                        is_cpu=manager.get("is_cpu", True),
                        real_inference=data.get("real_inference_enabled", False),
                        device_name=manager.get("device_name", ""),
                    )
                    return self._device_info
        except Exception as e:
            logger.warning(f"Failed to get NPU device info: {e}")
        return None

    async def generate_embeddings(
        self,
        texts: List[str],
        model_name: str = "nomic-embed-text",
        use_cache: bool = True
    ) -> Optional[EmbeddingResult]:
        """
        Generate embeddings using NPU worker.

        Args:
            texts: List of texts to embed
            model_name: Model to use for embedding
            use_cache: Whether to use NPU worker's cache

        Returns:
            EmbeddingResult if successful, None if failed
        """
        if not texts:
            return None

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/embedding/generate",
                json=texts,
                params={
                    "model_name": model_name,
                    "use_cache": str(use_cache).lower()
                },
                timeout=aiohttp.ClientTimeout(total=BATCH_TIMEOUT)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return EmbeddingResult(
                        embeddings=data.get("embeddings", []),
                        model_used=data.get("model_used", model_name),
                        processing_time_ms=data.get("processing_time_ms", 0),
                        device=data.get("device", "UNKNOWN"),
                        real_inference=data.get("real_inference", False),
                        texts_processed=data.get("texts_processed", len(texts)),
                        from_npu_worker=True,
                    )
                else:
                    logger.warning(f"NPU worker returned status {response.status}")
        except Exception as e:
            logger.warning(f"NPU worker embedding generation failed: {e}")

        return None

    async def generate_embedding(
        self,
        text: str,
        model_name: str = "nomic-embed-text"
    ) -> Optional[List[float]]:
        """
        Generate single embedding using NPU worker.

        Args:
            text: Text to embed
            model_name: Model to use

        Returns:
            Embedding vector if successful, None if failed
        """
        result = await self.generate_embeddings([text], model_name)
        if result and result.embeddings:
            return result.embeddings[0]
        return None

    async def get_stats(self) -> Optional[Dict[str, Any]]:
        """Get NPU worker statistics"""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/stats",
                timeout=aiohttp.ClientTimeout(total=HEALTH_CHECK_TIMEOUT)
            ) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.debug(f"Failed to get NPU stats: {e}")
        return None


# Global client instance with thread-safe initialization (Issue #662)
_npu_client: Optional[NPUClient] = None
_npu_client_lock = threading.Lock()


def get_npu_client() -> NPUClient:
    """Get or create global NPU client instance (thread-safe)."""
    global _npu_client
    if _npu_client is None:
        with _npu_client_lock:
            # Double-check after acquiring lock
            if _npu_client is None:
                _npu_client = NPUClient()
    return _npu_client


async def cleanup_npu_client():
    """Cleanup NPU client on shutdown"""
    global _npu_client
    if _npu_client:
        await _npu_client.close()
        _npu_client = None


# Embedding generation with automatic fallback
async def generate_embedding_with_fallback(
    text: str,
    model_name: str = "nomic-embed-text",
    ollama_host: str = None,
    ollama_port: str = None
) -> Optional[List[float]]:
    """
    Generate embedding with automatic fallback.

    Tries NPU worker first, falls back to Ollama if unavailable.

    Args:
        text: Text to embed
        model_name: Model name
        ollama_host: Ollama host for fallback
        ollama_port: Ollama port for fallback

    Returns:
        Embedding vector or None if all methods fail
    """
    client = get_npu_client()

    # Try NPU worker first
    if await client.is_available():
        embedding = await client.generate_embedding(text, model_name)
        if embedding:
            logger.debug(f"Generated embedding via NPU worker ({model_name})")
            return embedding

    # Fallback to Ollama - use SSOT config for defaults
    ollama_host = ollama_host or os.getenv("AUTOBOT_OLLAMA_HOST", _ssot.vm.ollama)
    ollama_port = ollama_port or os.getenv("AUTOBOT_OLLAMA_PORT", str(_ssot.port.ollama))
    ollama_url = f"http://{ollama_host}:{ollama_port}/api/embeddings"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ollama_url,
                json={"model": model_name, "prompt": text},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    embedding = data.get("embedding")
                    if embedding:
                        logger.debug(f"Generated embedding via Ollama ({model_name})")
                        return embedding
    except Exception as e:
        logger.warning(f"Ollama embedding generation failed: {e}")

    return None


async def generate_embeddings_batch_with_fallback(
    texts: List[str],
    model_name: str = "nomic-embed-text",
    max_concurrent: int = 5
) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts with fallback.

    Uses NPU worker for batch processing if available,
    otherwise falls back to parallel Ollama requests.
    """
    if not texts:
        return []

    client = get_npu_client()

    # Try NPU worker batch endpoint first
    if await client.is_available():
        result = await client.generate_embeddings(texts, model_name)
        if result and len(result.embeddings) == len(texts):
            logger.info(f"Generated {len(texts)} embeddings via NPU worker")
            return result.embeddings

    # Fallback to parallel Ollama requests
    semaphore = asyncio.Semaphore(max_concurrent)

    async def generate_one(text: str) -> Optional[List[float]]:
        async with semaphore:
            return await generate_embedding_with_fallback(text, model_name)

    tasks = [generate_one(text) for text in texts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert exceptions to None
    return [
        r if isinstance(r, list) else None
        for r in results
    ]
