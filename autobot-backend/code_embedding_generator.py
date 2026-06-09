# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Code Embedding Generator for Semantic Code Search

Generates code-specific embeddings using CodeBERT with NPU acceleration.
Supports function/class level embeddings for semantic code search.

Issue #207: NPU-Accelerated Semantic Code Search
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np

from autobot_shared.logging_manager import get_llm_logger
from knowledge.embedding_cache import get_embedding_cache
from worker_node import WorkerNode

logger = get_llm_logger("code_embedding_generator")

# CodeBERT embedding dimension
CODEBERT_EMBEDDING_DIM = 768


@dataclass
class CodeEmbeddingResult:
    """Result of code embedding generation."""

    embedding: np.ndarray
    device_used: str
    processing_time_ms: float
    model_name: str
    cache_hit: bool


class CodeEmbeddingGenerator:
    """
    Generate code embeddings using CodeBERT with NPU acceleration.

    Issue #207: Provides code-specific embeddings for semantic search.
    Uses OpenVINO for NPU acceleration when available.
    """

    def __init__(self):
        """Initialize the code embedding generator."""
        self.model_name = "microsoft/codebert-base"
        self.embedding_dim = CODEBERT_EMBEDDING_DIM
        self.tokenizer = None
        self.model = None
        self.openvino_model = None
        self.worker_node = WorkerNode()
        self.embedding_cache = get_embedding_cache()
        self.npu_available = False
        self.gpu_available = False
        self.initialized = False
        self._init_lock = asyncio.Lock()
        # Issue #3290: track actual OpenVINO compiled device for accurate metrics
        self._openvino_device = "cpu"

    async def initialize(self) -> None:
        """Initialize the CodeBERT model with hardware detection."""
        async with self._init_lock:
            if self.initialized:
                return

            logger.info("Initializing CodeBERT embedding generator...")
            start_time = time.time()

            try:
                await self._detect_hardware()
                await self._load_model()
                self.initialized = True
                init_time = (time.time() - start_time) * 1000
                logger.info(
                    "CodeBERT initialized in %.2fms (NPU: %s, GPU: %s)",
                    init_time,
                    self.npu_available,
                    self.gpu_available,
                )
            except Exception as e:
                logger.error("Failed to initialize CodeBERT: %s", e)
                raise

    async def _detect_hardware(self) -> None:
        """Detect available hardware accelerators."""
        try:
            capabilities = self.worker_node.detect_capabilities()
            self.npu_available = capabilities.get("openvino_npu_available", False)
            self.gpu_available = capabilities.get("cuda_available", False)

            if self.npu_available:
                logger.info("NPU acceleration available for CodeBERT")
            if self.gpu_available:
                logger.info("GPU acceleration available for CodeBERT")
            if not self.npu_available and not self.gpu_available:
                logger.info("Using CPU for CodeBERT embeddings")
        except Exception as e:
            logger.warning("Hardware detection failed: %s", e)
            self.npu_available = False
            self.gpu_available = False

    async def _load_model(self) -> None:
        """Load CodeBERT model with appropriate backend."""

        def _load_sync():
            from transformers import AutoModel, AutoTokenizer

            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, resume_download=True
            )  # nosec B615 - HuggingFace model loaded by name; revision pinning managed operationally
            self.model = AutoModel.from_pretrained(
                self.model_name, resume_download=True
            )  # nosec B615 - HuggingFace model loaded by name; revision pinning managed operationally

            if self.npu_available:
                self._convert_to_openvino()
            elif self.gpu_available:
                import torch

                if torch.cuda.is_available():
                    self.model = self.model.cuda()
                    logger.info("CodeBERT loaded on GPU")
            else:
                logger.info("CodeBERT loaded on CPU")

        await asyncio.to_thread(_load_sync)

    def _convert_to_openvino(self) -> None:
        """Convert CodeBERT to OpenVINO IR and compile on NPU when available.

        Issue #3290: Explicitly targets NPU device; records the compiled device
        so _compute_with_openvino can report the correct device label in metrics.
        """
        try:
            import torch
            from openvino import convert_model
            from openvino.runtime import Core

            logger.info("Converting CodeBERT to OpenVINO IR for NPU...")
            self.model.train(False)

            dummy_input_ids = torch.zeros(1, 512, dtype=torch.long)
            dummy_attention_mask = torch.ones(1, 512, dtype=torch.long)

            ov_model = convert_model(
                self.model,
                example_input={
                    "input_ids": dummy_input_ids,
                    "attention_mask": dummy_attention_mask,
                },
            )

            core = Core()
            devices = core.available_devices
            # Issue #3290: prefer NPU, fall back to GPU then CPU
            if "NPU" in devices:
                target_device = "NPU"
            elif "GPU" in devices:
                target_device = "GPU"
            else:
                target_device = "CPU"

            self.openvino_model = core.compile_model(ov_model, target_device)
            # Record the actual device so _compute_with_openvino reports correctly
            self._openvino_device = target_device.lower()
            logger.info(
                "CodeBERT compiled for %s (NPU available: %s)",
                target_device,
                "NPU" in devices,
            )

        except Exception as e:
            logger.warning("OpenVINO conversion failed: %s, using PyTorch", e)
            self.openvino_model = None
            self._openvino_device = "cpu"
            self.npu_available = False

    def _get_cache_key(self, code: str, language: str) -> str:
        """Generate cache key for code embedding."""
        content = f"codebert:{language}:{code}"
        return hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

    async def generate_embedding(self, code: str, language: str = "python") -> CodeEmbeddingResult:
        """
        Generate embedding for a code snippet.

        Args:
            code: Source code to embed
            language: Programming language of the code

        Returns:
            CodeEmbeddingResult with embedding and metadata
        """
        if not self.initialized:
            await self.initialize()

        start_time = time.time()
        cache_key = self._get_cache_key(code, language)

        cached = await self.embedding_cache.get(cache_key)
        if cached is not None:
            return CodeEmbeddingResult(
                embedding=np.array(cached),
                device_used="cached",
                processing_time_ms=(time.time() - start_time) * 1000,
                model_name=self.model_name,
                cache_hit=True,
            )

        embedding, device_used = await self._compute_embedding(code, language)

        await self.embedding_cache.put(cache_key, embedding.tolist())

        return CodeEmbeddingResult(
            embedding=embedding,
            device_used=device_used,
            processing_time_ms=(time.time() - start_time) * 1000,
            model_name=self.model_name,
            cache_hit=False,
        )

    async def _compute_embedding(self, code: str, language: str) -> Tuple[np.ndarray, str]:
        """Compute embedding using available hardware."""
        formatted_code = f"# {language}\n{code}"

        if self.openvino_model is not None:
            return await self._compute_with_openvino(formatted_code)
        elif self.gpu_available:
            return await self._compute_with_gpu(formatted_code)
        else:
            return await self._compute_with_cpu(formatted_code)

    async def _compute_with_openvino(self, code: str) -> Tuple[np.ndarray, str]:
        """Compute embedding using OpenVINO on the compiled device (NPU/GPU/CPU).

        Issue #3290: Returns the actual compiled device label instead of
        hard-coding "npu", enabling accurate device reporting in search metrics.
        """

        def _compute_sync():
            import numpy as np

            inputs = self.tokenizer(
                code,
                return_tensors="np",
                padding="max_length",
                truncation=True,
                max_length=512,
            )

            result = self.openvino_model(
                {
                    "input_ids": inputs["input_ids"],
                    "attention_mask": inputs["attention_mask"],
                }
            )

            last_hidden_state = result[0]
            embedding = np.mean(last_hidden_state[0], axis=0)
            return embedding

        embedding = await asyncio.to_thread(_compute_sync)
        # Issue #3290: report the actual device the model was compiled for
        return embedding, self._openvino_device

    async def _compute_with_gpu(self, code: str) -> Tuple[np.ndarray, str]:
        """Compute embedding using GPU."""

        def _compute_sync():
            import torch

            inputs = self.tokenizer(
                code,
                return_tensors="pt",
                padding="max_length",
                truncation=True,
                max_length=512,
            )

            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)

            last_hidden_state = outputs.last_hidden_state
            embedding = torch.mean(last_hidden_state[0], dim=0).cpu().numpy()
            return embedding

        embedding = await asyncio.to_thread(_compute_sync)
        return embedding, "gpu"

    async def _compute_with_cpu(self, code: str) -> Tuple[np.ndarray, str]:
        """Compute embedding using CPU."""

        def _compute_sync():
            import torch

            inputs = self.tokenizer(
                code,
                return_tensors="pt",
                padding="max_length",
                truncation=True,
                max_length=512,
            )

            with torch.no_grad():
                outputs = self.model(**inputs)

            last_hidden_state = outputs.last_hidden_state
            embedding = torch.mean(last_hidden_state[0], dim=0).numpy()
            return embedding

        embedding = await asyncio.to_thread(_compute_sync)
        return embedding, "cpu"

    async def _batch_compute_with_openvino(self, formatted_snippets: List[str]) -> List[Tuple[np.ndarray, str]]:
        """Batch-compute embeddings via OpenVINO for NPU/GPU efficiency.

        Issue #3290: Running a single batched inference on the NPU is
        significantly faster than N sequential single-sample calls because it
        amortises the host-device transfer overhead.

        Args:
            formatted_snippets: Pre-formatted code strings

        Returns:
            List of (embedding, device_label) tuples
        """
        device_label = self._openvino_device

        def _batch_sync() -> List[np.ndarray]:
            import numpy as np

            inputs = self.tokenizer(
                formatted_snippets,
                return_tensors="np",
                padding="max_length",
                truncation=True,
                max_length=512,
            )
            result = self.openvino_model(
                {
                    "input_ids": inputs["input_ids"],
                    "attention_mask": inputs["attention_mask"],
                }
            )
            # result[0] shape: (batch, seq_len, hidden_dim) → mean over seq_len
            last_hidden_state = result[0]
            return [np.mean(last_hidden_state[i], axis=0) for i in range(len(formatted_snippets))]

        embeddings = await asyncio.to_thread(_batch_sync)
        return [(emb, device_label) for emb in embeddings]

    async def batch_generate(
        self, code_snippets: List[Tuple[str, str]], batch_size: int = 8
    ) -> List[CodeEmbeddingResult]:
        """Generate embeddings for multiple code snippets.

        Issue #3290: When the OpenVINO model is compiled on NPU/GPU the entire
        batch is submitted as a single inference request for maximum throughput.
        Falls back to parallel individual calls when only a PyTorch CPU/GPU
        backend is available.

        Args:
            code_snippets: List of (code, language) tuples
            batch_size: Number of snippets per inference batch

        Returns:
            List of CodeEmbeddingResult for each snippet
        """
        if not self.initialized:
            await self.initialize()

        results: List[CodeEmbeddingResult] = []

        for i in range(0, len(code_snippets), batch_size):
            batch = code_snippets[i : i + batch_size]
            start_time = time.time()

            if self.openvino_model is not None:
                # Issue #3290: single batched NPU inference — much faster than N serial calls
                formatted = [f"# {lang}\n{code}" for code, lang in batch]
                raw_pairs = await self._batch_compute_with_openvino(formatted)
                for j, (embedding, device_used) in enumerate(raw_pairs):
                    code, lang = batch[j]
                    cache_key = self._get_cache_key(code, lang)
                    await self.embedding_cache.put(cache_key, embedding.tolist())
                    results.append(
                        CodeEmbeddingResult(
                            embedding=embedding,
                            device_used=device_used,
                            processing_time_ms=(time.time() - start_time) * 1000,
                            model_name=self.model_name,
                            cache_hit=False,
                        )
                    )
            else:
                batch_results = await asyncio.gather(*[self.generate_embedding(code, lang) for code, lang in batch])
                results.extend(batch_results)

        return results

    def get_embedding_dim(self) -> int:
        """Return the embedding dimension."""
        return self.embedding_dim

    async def get_stats(self) -> Dict[str, Any]:
        """Get generator statistics including NPU utilisation.

        Issue #3290: adds compiled_device and npu_utilization_reported fields
        so callers can confirm the NPU is actually being used.
        """
        cache_stats = self.embedding_cache.get_stats()
        using_openvino = self.openvino_model is not None
        return {
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "initialized": self.initialized,
            "npu_available": self.npu_available,
            "gpu_available": self.gpu_available,
            "using_openvino": using_openvino,
            # Issue #3290: report the actual compiled device for metrics
            "compiled_device": self._openvino_device if using_openvino else "pytorch",
            "npu_utilization_reported": using_openvino and self._openvino_device == "npu",
            "cache_stats": cache_stats,
        }


from autobot_shared.singleton_factory import async_lazy_singleton


async def _init_code_embedding_generator() -> CodeEmbeddingGenerator:
    instance = CodeEmbeddingGenerator()
    await instance.initialize()
    return instance


get_code_embedding_generator = async_lazy_singleton(_init_code_embedding_generator)
