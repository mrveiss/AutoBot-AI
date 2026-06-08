# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Semantic Chunking Module (CPU path).

Issue #5363: shared pipeline lives in `semantic_chunker_base.py`. This
module contains only the CPU-specific embedding-compute + model-init
plus the public factory `get_semantic_chunker()`.

Public API (preserved):
    - AutoBotSemanticChunker
    - SemanticChunk (re-exported from base)
    - get_semantic_chunker()
"""

from typing import List

import numpy as np

from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.singleton_factory import lazy_singleton
from constants.threshold_constants import RetryConfig, TimingConstants
from utils.semantic_chunker_base import SemanticChunk, SemanticChunkerBase

__all__ = ["AutoBotSemanticChunker", "SemanticChunk", "get_semantic_chunker"]

logger = get_llm_logger("semantic_chunker")


class AutoBotSemanticChunker(SemanticChunkerBase):
    """
    CPU / adaptive-batch semantic chunker.

    Uses sentence-transformer embeddings with adaptive batch-size and
    worker-count selection based on CPU load and whether CUDA happens to
    be available. Falls back through `all-mpnet-base-v2` and
    `all-MiniLM-L12-v2` if the primary model fails to load.
    """

    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        percentile_threshold: float = 95.0,
        min_chunk_size: int = 100,
        max_chunk_size: int = 1000,
        overlap_sentences: int = 1,
    ):
        super().__init__(
            embedding_model=embedding_model,
            percentile_threshold=percentile_threshold,
            min_chunk_size=min_chunk_size,
            max_chunk_size=max_chunk_size,
            overlap_sentences=overlap_sentences,
        )
        logger.info("SemanticChunker initialized with model: %s", embedding_model)

    # ------------------------------------------------------------------
    # Metadata tagging — identifies this backend in chunk metadata
    # ------------------------------------------------------------------

    def _extra_chunk_metadata(self) -> dict:
        return {
            "chunking_method": "semantic_percentile",
            "percentile_threshold": self.percentile_threshold,
        }

    # ------------------------------------------------------------------
    # System / GPU detection helpers (Issue #665)
    # ------------------------------------------------------------------

    def _check_gpu_availability(self) -> bool:
        import torch

        return (
            torch.cuda.is_available()
            and self._embedding_model is not None
            and next(self._embedding_model.parameters()).device.type == "cuda"
        )

    def _get_system_info_for_batching(self) -> tuple[int, float, bool]:
        import os

        import psutil

        cpu_count = os.cpu_count() or 4
        cpu_load = psutil.cpu_percent(interval=0.1)
        has_gpu = self._check_gpu_availability()
        return cpu_count, cpu_load, has_gpu

    def _get_adaptive_batch_params(
        self, num_sentences: int, cpu_load: float, cpu_count: int, has_gpu: bool
    ) -> tuple[int, int]:
        """Adaptive (max_workers, batch_size) based on load + hardware (Issue #281)."""
        if has_gpu:
            if cpu_load > 80:
                max_workers = min(4, cpu_count // 4)
                batch_size = min(50, num_sentences)
            elif cpu_load > 50:
                max_workers = min(8, cpu_count // 2)
                batch_size = min(100, num_sentences)
            else:
                max_workers = min(12, cpu_count)
                batch_size = min(200, num_sentences)
        else:
            if cpu_load > 80:
                max_workers = min(2, cpu_count // 8)
                batch_size = min(10, num_sentences)
            elif cpu_load > 50:
                max_workers = min(4, cpu_count // 4)
                batch_size = min(25, num_sentences)
            else:
                max_workers = min(6, cpu_count // 2)
                batch_size = min(50, num_sentences)

        return max_workers, batch_size

    # ------------------------------------------------------------------
    # Model loading (Issue #333)
    # ------------------------------------------------------------------

    def _detect_device(self) -> str:
        import torch

        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            gpu_name = torch.cuda.get_device_name(0) if gpu_count > 0 else "Unknown"
            logger.info("Using CUDA GPU: %s (device count: %d)", gpu_name, gpu_count)
            return "cuda"

        logger.info("CUDA not available, using CPU for embeddings")
        return "cpu"

    def _apply_gpu_precision(self, model, device: str):
        import torch

        if device != "cuda":
            return model

        try:
            param_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
            if param_count == 0:
                logger.warning("Model parameters not properly loaded, skipping precision conversion")
                return model

            has_meta_tensors = any(p.device.type == "meta" for p in model.parameters())

            if has_meta_tensors:
                model = model.to_empty(device=device, dtype=torch.float16)
                logger.info("Converted meta tensors to FP16 on GPU")
            else:
                model = model.to(device, dtype=torch.float16)
                logger.info("Enabled FP16 mixed precision for GPU inference")

            return model

        except Exception as tensor_error:
            logger.warning("FP16 conversion failed: %s, trying FP32", tensor_error)
            try:
                return model.to(device, dtype=torch.float32)
            except Exception as precision_error:
                logger.warning("Could not enable FP16: %s, using FP32", precision_error)
                return model.to(device)

    def _load_model_with_retry(self, device: str):
        import time

        from sentence_transformers import SentenceTransformer

        max_retries = RetryConfig.DEFAULT_RETRIES
        retry_delay = TimingConstants.SERVICE_STARTUP_DELAY

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(
                        "Model loading attempt %d/%d after %ss delay...",
                        attempt + 1,
                        max_retries,
                        retry_delay,
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2

                return SentenceTransformer(self.embedding_model_name, device=device)

            except Exception as load_error:
                error_str = str(load_error).lower()
                is_rate_limit = "429" in error_str or "rate limit" in error_str or "http error" in error_str

                if not is_rate_limit:
                    raise

                if attempt >= max_retries - 1:
                    logger.error("Max retries exceeded for HuggingFace rate limiting: %s", load_error)
                    raise

                logger.warning(
                    "HuggingFace rate limit hit (attempt %d), retrying in %ds...",
                    attempt + 1,
                    retry_delay,
                )

        raise RuntimeError("Model loading failed after retries")

    def _optimize_loaded_model(self, model, device: str):
        from sentence_transformers import SentenceTransformer

        try:
            actual_device = next(model.parameters()).device
            logger.info(
                "Embedding model '%s' loaded on device: %s",
                self.embedding_model_name,
                actual_device,
            )
            return self._apply_gpu_precision(model, device)

        except Exception as model_load_error:
            logger.warning(
                "Failed to optimize model '%s' on %s: %s",
                self.embedding_model_name,
                device,
                model_load_error,
            )

            if device != "cpu":
                logger.info("Attempting fallback to CPU...")
                return SentenceTransformer(self.embedding_model_name, device="cpu")

            raise

    async def _try_fallback_models(self) -> None:
        from sentence_transformers import SentenceTransformer

        for model_name in ("all-mpnet-base-v2", "all-MiniLM-L12-v2"):
            try:
                logger.info("Attempting fallback model loading on CPU: %s", model_name)
                self._embedding_model = SentenceTransformer(model_name)
                logger.warning("Fallback to %s embedding model on CPU", model_name)
                return
            except Exception as fallback_error:
                logger.error("Failed to load fallback model %s: %s", model_name, fallback_error)

        raise RuntimeError("Could not initialize any embedding model")

    async def _initialize_model(self) -> None:
        """Lazy initialize the sentence-transformer model on first use (async, thread-pool)."""
        if self._embedding_model is not None:
            return

        try:
            import asyncio
            import concurrent.futures

            def load_model():
                device = self._detect_device()
                model = self._load_model_with_retry(device)
                return self._optimize_loaded_model(model, device)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                logger.info(
                    "Loading embedding model '%s' in background thread...",
                    self.embedding_model_name,
                )
                self._embedding_model = await asyncio.get_running_loop().run_in_executor(executor, load_model)
                logger.info("Embedding model loading completed")

        except Exception as e:
            logger.error("Failed to load embedding model %s: %s", self.embedding_model_name, e)
            await self._try_fallback_models()

    # ------------------------------------------------------------------
    # Embedding compute
    # ------------------------------------------------------------------

    async def _process_embedding_batches(
        self, sentences: List[str], batch_size: int, max_workers: int
    ) -> List[np.ndarray]:
        """Thread-pool-driven batch processing (Issue #665)."""
        import asyncio
        import concurrent.futures

        all_embeddings: List[np.ndarray] = []

        for i in range(0, len(sentences), batch_size):
            batch_sentences = sentences[i : i + batch_size]

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                embeddings = await asyncio.get_running_loop().run_in_executor(
                    executor,
                    lambda: self._embedding_model.encode(
                        batch_sentences,
                        convert_to_tensor=False,
                        show_progress_bar=False,
                    ),
                )
                all_embeddings.append(embeddings)

            await asyncio.sleep(TimingConstants.YIELD_INTERVAL)

            if len(sentences) > 20:
                progress = min(100, int((i + batch_size) / len(sentences) * 100))
                logger.debug("Embedding progress: %d%%", progress)

        return all_embeddings

    def _create_fallback_embeddings(self, num_sentences: int) -> np.ndarray:
        """Zero-embedding fallback when compute fails (Issue #665)."""
        try:
            dim = self._embedding_model.get_sentence_embedding_dimension()
            return np.zeros((num_sentences, dim))
        except Exception:
            return np.zeros((num_sentences, 384))

    async def _compute_embeddings(self, sentences: List[str]) -> np.ndarray:
        """Async embedding compute with adaptive batching (Issue #665)."""
        await self._initialize_model()

        try:
            cpu_count, cpu_load, has_gpu = self._get_system_info_for_batching()
            max_workers, batch_size = self._get_adaptive_batch_params(len(sentences), cpu_load, cpu_count, has_gpu)

            logger.info(
                "Processing %d sentences with %d workers, batch_size=%d, CPU load=%s%%",
                len(sentences),
                max_workers,
                batch_size,
                cpu_load,
            )

            all_embeddings = await self._process_embedding_batches(sentences, batch_size, max_workers)

            if len(all_embeddings) == 1:
                return np.array(all_embeddings[0])
            return np.vstack(all_embeddings)

        except Exception as e:
            logger.error("Error computing sentence embeddings: %s", e)
            return self._create_fallback_embeddings(len(sentences))

    # Backwards-compatible alias: `npu_semantic_search._generate_embedding_gpu_fallback`
    # still imports and calls `_compute_sentence_embeddings_async` directly.
    async def _compute_sentence_embeddings_async(self, sentences: List[str]) -> np.ndarray:
        return await self._compute_embeddings(sentences)

    # ------------------------------------------------------------------
    # Synchronous entry points — kept for two live external callers:
    #   autobot-backend/npu_semantic_search.py:521  (CPU final fallback)
    #   autobot-infrastructure/.../npu_performance_measurement.py:187/192
    # ------------------------------------------------------------------

    def _sync_try_fallback_models(self, device: str) -> None:
        """Try loading fallback models synchronously."""
        from sentence_transformers import SentenceTransformer

        self._embedding_model = SentenceTransformer("all-mpnet-base-v2")

        if device == "cuda":
            try:
                import torch

                has_meta_tensors = any(p.device.type == "meta" for p in self._embedding_model.parameters())
                if has_meta_tensors:
                    self._embedding_model = self._embedding_model.to_empty(device=device)
                else:
                    self._embedding_model = self._embedding_model.to(device)
            except Exception as device_error:
                logger.warning("Failed to move model to GPU: %s, using CPU", device_error)
                device = "cpu"
                # Reference `torch` to satisfy linters about unused import in the try block.
                _ = torch

        logger.warning("Fallback to all-mpnet-base-v2 embedding model on %s", device)

    def _sync_initialize_model(self) -> None:
        """Synchronous model initialization for non-async fallback paths (blocking)."""
        if self._embedding_model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            device = self._detect_device()
            self._embedding_model = SentenceTransformer(self.embedding_model_name, device=device)

            actual_device = next(self._embedding_model.parameters()).device
            logger.info(
                "Embedding model '%s' loaded on device: %s",
                self.embedding_model_name,
                actual_device,
            )

            self._embedding_model = self._apply_gpu_precision(self._embedding_model, device)

        except Exception as e:
            logger.error("Failed to load embedding model %s: %s", self.embedding_model_name, e)
            try:
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
                self._sync_try_fallback_models(device)
            except Exception as fallback_error:
                logger.error("Failed to load fallback model: %s", fallback_error)
                raise RuntimeError("Could not initialize any embedding model")

    def _compute_sentence_embeddings(self, sentences: List[str]) -> np.ndarray:
        """Synchronous embedding wrapper for backward compatibility.

        Live callers: `npu_semantic_search._generate_fallback_embedding` and
        `autobot-infrastructure/.../npu_performance_measurement.py`.

        #7469: previously this had a hand-rolled try-loop / sync-fallback
        pattern that BLOCKED the event loop on the in-async path
        (running encoder synchronously inline). Migrated to the shared
        ``run_or_schedule`` helper which uses a threadpool detour in
        the in-async case — same final result, doesn't block the loop.
        Caller still sees the same return shape.
        """
        from autobot_shared.async_compat import run_or_schedule

        return run_or_schedule(self._compute_sentence_embeddings_async(sentences))

    # ------------------------------------------------------------------
    # Coherence scoring (CPU-only utility — not on hot chunk_text path)
    # ------------------------------------------------------------------

    async def _calculate_chunk_coherence_async(self, sentences: List[str]) -> float:
        """Semantic coherence score for a chunk (0-1, higher is more coherent)."""
        if len(sentences) <= 1:
            return 1.0

        try:
            embeddings = await self._compute_sentence_embeddings_async(sentences)
            if len(embeddings) <= 1:
                return 1.0

            from sklearn.metrics.pairwise import cosine_similarity

            similarities: List[float] = []
            for i in range(len(embeddings)):
                for j in range(i + 1, len(embeddings)):
                    similarity = cosine_similarity(embeddings[i].reshape(1, -1), embeddings[j].reshape(1, -1))[0][0]
                    similarities.append(similarity)

            return float(np.mean(similarities)) if similarities else 1.0
        except Exception as e:
            logger.error("Error calculating chunk coherence: %s", e)
            return 0.5


# ----------------------------------------------------------------------
# Public factory (preserves singleton semantics for all 15 CPU callers)
# ----------------------------------------------------------------------

get_semantic_chunker = lazy_singleton(AutoBotSemanticChunker)
