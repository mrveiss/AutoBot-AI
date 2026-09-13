# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Serving a task: embeddings, semantic search and the cache (#68, #15642).

The request-time half of the worker. Dispatches a task to the right handler,
generates embeddings through the model manager (falling back to a deterministic
mock when no NPU session exists), answers semantic-search queries, and owns the
cache key and hit-rate arithmetic the embedding cache is measured by.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import asyncio
import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

import numpy as np
from worker_settings import DEFAULT_NPU_BATCH_SIZE, EMBEDDING_DIM_DEFAULT, EMBEDDING_DIM_NOMIC

logger = logging.getLogger(__name__)


class WorkerInferenceMixin:
    """Task dispatch, embedding generation and search for :class:`WindowsNPUWorker`."""

    async def process_task(self, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process task"""
        task_type = task_data.get("task_type")
        model_name = task_data.get("model_name")
        input_data = task_data.get("input_data", {})

        if model_name not in self.loaded_models:
            await self.load_and_optimize_model(model_name)

        self.loaded_models[model_name]["last_used"] = datetime.now().isoformat()

        if task_type == "embedding_generation":
            return await self.process_embedding_task(input_data, model_name)
        elif task_type == "semantic_search":
            return await self.process_search_task(input_data, model_name)
        else:
            raise ValueError(f"Unsupported task type: {task_type}")

    async def process_embedding_task(self, input_data: Dict[str, Any], model_name: str) -> Dict[str, Any]:
        """Process embedding task with thread-safe cache and stats (Issue #68)"""
        text = input_data.get("text", "")
        cache_key = self._generate_cache_key(text, model_name)

        # Check cache (thread-safe LRU cache with TTL)
        cached_embedding = await self.embedding_cache.get(cache_key)
        if cached_embedding is not None:
            await self.task_stats.increment("cache_hits")
            return {
                "embedding": cached_embedding,
                "model_used": model_name,
                "device": "NPU_CACHED",
                "cache_hit": True,
            }

        start_time = time.time()
        embedding = self._generate_embedding(text, model_name)
        processing_time = (time.time() - start_time) * 1000

        # Store in cache (LRU cache handles eviction automatically)
        await self.embedding_cache.set(cache_key, embedding)

        await self.task_stats.increment("embedding_generations")

        return {
            "embedding": embedding,
            "model_used": model_name,
            "device": "NPU" if self.npu_available else "CPU",
            "processing_time_ms": processing_time,
            "cache_hit": False,
        }

    async def generate_npu_embeddings(
        self,
        texts: List[str],
        model_name: str,
        use_cache: bool,
        optimization_level: str,
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts with thread-safe cache (Issue #68)"""
        embeddings = []
        batch_size = self.npu_optimization.get("batch_size", DEFAULT_NPU_BATCH_SIZE)

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_embeddings = []

            for text in batch_texts:
                cache_key = self._generate_cache_key(text, model_name)

                if use_cache:
                    cached = await self.embedding_cache.get(cache_key)
                    if cached is not None:
                        batch_embeddings.append(cached)
                        await self.task_stats.increment("cache_hits")
                        continue

                embedding = self._generate_embedding(text, model_name)
                batch_embeddings.append(embedding)

                if use_cache:
                    await self.embedding_cache.set(cache_key, embedding)

            embeddings.extend(batch_embeddings)
            await asyncio.sleep(0.001)

        return embeddings

    async def perform_semantic_search(
        self,
        query_text: str,
        document_embeddings: List[List[float]],
        document_metadata: List[Dict[str, Any]],
        top_k: int,
        similarity_threshold: float,
    ) -> List[Dict[str, Any]]:
        """Perform semantic search with thread-safe stats (Issue #68)"""
        query_embedding = await self.generate_npu_embeddings([query_text], "nomic-embed-text", True, "speed")
        query_vector = np.array(query_embedding[0])

        document_vectors = np.array(document_embeddings)

        if self.npu_available:
            await asyncio.sleep(0.005)
        else:
            await asyncio.sleep(0.02)

        # Compute cosine similarities
        query_norm = query_vector / np.linalg.norm(query_vector)
        doc_norms = document_vectors / np.linalg.norm(document_vectors, axis=1, keepdims=True)
        similarities = np.dot(doc_norms, query_norm)

        results = []
        for i, similarity in enumerate(similarities):
            if similarity >= similarity_threshold:
                results.append(
                    {
                        "index": i,
                        "similarity": float(similarity),
                        "metadata": (document_metadata[i] if i < len(document_metadata) else {}),
                    }
                )

        results.sort(key=lambda x: x["similarity"], reverse=True)
        await self.task_stats.increment("semantic_searches")

        return results[:top_k]

    def _generate_embedding(self, text: str, model_name: str) -> List[float]:
        """
        Generate embedding using real OpenVINO inference or mock fallback.

        Issue #640: Replaces mock embeddings with real NPU inference.
        Falls back to mock if real inference unavailable.
        """
        # Issue #640: Use real inference if available
        if self._use_real_inference and self._model_manager is not None:
            try:
                embedding = self._model_manager.generate_embedding(text, model_name)
                return embedding
            except Exception as e:
                logger.warning(f"Real inference failed for {model_name}, using mock: {e}")
                # Fall through to mock implementation

        # Mock implementation (fallback)
        return self._generate_mock_embedding(text, model_name)

    def _generate_mock_embedding(self, text: str, model_name: str) -> List[float]:
        """Generate mock embedding using deterministic hash (fallback)."""
        import random

        # Use hashlib from top-level imports for deterministic embedding
        hash_obj = hashlib.md5(f"{text}{model_name}".encode())
        random.seed(int(hash_obj.hexdigest(), 16) % (2**32))

        # Use constants for embedding dimensions
        dim = EMBEDDING_DIM_NOMIC if "nomic" in model_name.lower() else EMBEDDING_DIM_DEFAULT
        embedding = [random.uniform(-1, 1) for _ in range(dim)]

        # Normalize
        norm = sum(x**2 for x in embedding) ** 0.5
        embedding = [x / norm for x in embedding]

        return embedding

    def _generate_cache_key(self, text: str, model_name: str) -> str:
        """Generate cache key using hashlib from top-level imports"""
        return hashlib.md5(f"{text}:{model_name}".encode()).hexdigest()

    async def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate (async for thread-safe stats access)"""
        total = await self.task_stats.get("embedding_generations")
        hits = await self.task_stats.get("cache_hits")
        return (hits / total * 100) if total > 0 else 0.0
