# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.knowledge.embedding_cache import get_embedding_cache
from autobot_shared.logging_manager import get_llm_logger
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

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModel.from_pretrained(self.model_name)

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
        """Convert CodeBERT to OpenVINO IR for NPU acceleration."""
        try:
            import torch
            from openvino import convert_model
            from openvino.runtime import Core

            logger.info("Converting CodeBERT to OpenVINO IR for NPU...")
            self.model.eval()

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
            target_device = "NPU" if "NPU" in devices else "CPU"

            self.openvino_model = core.compile_model(ov_model, target_device)
            logger.info("CodeBERT compiled for %s", target_device)

        except Exception as e:
            logger.warning("OpenVINO conversion failed: %s, using PyTorch", e)
            self.openvino_model = None
            self.npu_available = False

    def _get_cache_key(self, code: str, language: str) -> str:
        """Generate cache key for code embedding."""
        content = f"codebert:{language}:{code}"
        return hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

    async def generate_embedding(
        self, code: str, language: str = "python"
    ) -> CodeEmbeddingResult:
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

    async def _compute_embedding(
        self, code: str, language: str
    ) -> Tuple[np.ndarray, str]:
        """Compute embedding using available hardware."""
        formatted_code = f"# {language}\n{code}"

        if self.openvino_model is not None:
            return await self._compute_with_openvino(formatted_code)
        elif self.gpu_available:
            return await self._compute_with_gpu(formatted_code)
        else:
            return await self._compute_with_cpu(formatted_code)

    async def _compute_with_openvino(self, code: str) -> Tuple[np.ndarray, str]:
        """Compute embedding using OpenVINO/NPU."""

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
        return embedding, "npu"

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

    async def batch_generate(
        self, code_snippets: List[Tuple[str, str]], batch_size: int = 8
    ) -> List[CodeEmbeddingResult]:
        """
        Generate embeddings for multiple code snippets.

        Args:
            code_snippets: List of (code, language) tuples
            batch_size: Number of snippets to process in parallel

        Returns:
            List of CodeEmbeddingResult for each snippet
        """
        if not self.initialized:
            await self.initialize()

        results = []

        for i in range(0, len(code_snippets), batch_size):
            batch = code_snippets[i : i + batch_size]
            batch_results = await asyncio.gather(
                *[self.generate_embedding(code, lang) for code, lang in batch]
            )
            results.extend(batch_results)

        return results

    def get_embedding_dim(self) -> int:
        """Return the embedding dimension."""
        return self.embedding_dim

    async def get_stats(self) -> Dict[str, Any]:
        """Get generator statistics."""
        cache_stats = self.embedding_cache.get_stats()
        return {
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "initialized": self.initialized,
            "npu_available": self.npu_available,
            "gpu_available": self.gpu_available,
            "using_openvino": self.openvino_model is not None,
            "cache_stats": cache_stats,
        }


# Singleton instance
_code_embedding_generator: Optional[CodeEmbeddingGenerator] = None
_code_embedding_lock = asyncio.Lock()


async def get_code_embedding_generator() -> CodeEmbeddingGenerator:
    """Get or create the code embedding generator instance."""
    global _code_embedding_generator
    if _code_embedding_generator is None:
        async with _code_embedding_lock:
            if _code_embedding_generator is None:
                _code_embedding_generator = CodeEmbeddingGenerator()
                await _code_embedding_generator.initialize()
    return _code_embedding_generator
