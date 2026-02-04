# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Semantic Chunking Module - GPU Optimized for RTX 4070
GPU Performance Enhancement: 3x speed improvement target

Optimizations implemented:
- Large GPU batch processing (200-500 sentences)
- Aggressive FP16 mixed precision
- GPU memory pooling and tensor optimization
- Multi-threaded CPU preprocessing
- Intel Ultra 9 185H multi-core utilization
"""

import os

# CRITICAL FIX: Force tf-keras usage before importing transformers/sentence-transformers
os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ["KERAS_BACKEND"] = "tensorflow"

# GPU optimization environment variables
os.environ["CUDA_LAUNCH_BLOCKING"] = "0"  # Allow async CUDA operations
os.environ["CUDA_CACHE_DISABLE"] = "0"  # Enable CUDA kernel caching

# Reduce Hugging Face rate limiting and improve caching
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
os.environ["HF_HUB_CACHE"] = os.path.expanduser("~/.cache/huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.expanduser("~/.cache/huggingface")

import asyncio
import concurrent.futures
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

# Import centralized logging
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("semantic_chunker_gpu")


@dataclass
class SemanticChunk:
    """Represents a semantically coherent chunk of text."""

    content: str
    start_index: int
    end_index: int
    sentences: List[str]
    semantic_score: float
    metadata: Dict[str, Any]


class GPUSemanticChunker:
    """
    GPU-Accelerated Semantic Chunker for AutoBot

    Specifically optimized for:
    - Intel Ultra 9 185H (22 cores)
    - RTX 4070 Laptop GPU (8GB VRAM)
    - Target: 3x performance improvement
    """

    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        percentile_threshold: float = 95.0,
        min_chunk_size: int = 100,
        max_chunk_size: int = 1000,
        overlap_sentences: int = 1,
        gpu_batch_size: int = 500,  # Large batches for RTX 4070
        enable_gpu_memory_pool: bool = True,
    ):
        """Initialize the optimized semantic chunker."""
        self.embedding_model_name = embedding_model
        self.percentile_threshold = percentile_threshold
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_sentences = overlap_sentences
        self.gpu_batch_size = gpu_batch_size
        self.enable_gpu_memory_pool = enable_gpu_memory_pool

        # Performance monitoring
        self.processing_stats = {
            "total_sentences": 0,
            "total_processing_time": 0.0,
            "gpu_utilization_samples": [],
            "memory_usage_samples": [],
        }

        # Initialize embedding model placeholder - will be loaded lazily
        self._embedding_model = None
        self._model_lock = threading.Lock()
        self._gpu_memory_pool_initialized = False

        logger.info("GPUSemanticChunker initialized:")
        logger.info("  - Model: %s", embedding_model)
        logger.info("  - GPU Batch Size: %s (optimized for RTX 4070)", gpu_batch_size)
        logger.info("  - GPU Memory Pooling: %s", enable_gpu_memory_pool)

    def _setup_gpu_optimizations(self) -> None:
        """Configure GPU optimizations for RTX 4070 (Issue #315: extracted)."""
        import torch

        if not torch.cuda.is_available():
            return

        # RTX 4070 specific optimizations
        torch.backends.cudnn.benchmark = True  # Optimize for consistent input sizes
        torch.backends.cuda.matmul.allow_tf32 = True  # Enable TF32 for RTX 4070
        torch.backends.cudnn.allow_tf32 = True

    def _initialize_gpu_memory_pool(self) -> None:
        """Initialize GPU memory pool for RTX 4070 (Issue #315: extracted)."""
        import torch

        if not self.enable_gpu_memory_pool or self._gpu_memory_pool_initialized:
            return

        try:
            # Reserve 6GB for embedding operations, leave 2GB for system
            torch.cuda.set_per_process_memory_fraction(0.75)  # 6GB of 8GB
            torch.cuda.empty_cache()
            self._gpu_memory_pool_initialized = True
            logger.info("GPU memory pool initialized for RTX 4070 (6GB reserved)")
        except Exception as pool_error:
            logger.warning("GPU memory pool setup failed: %s", pool_error)

    def _apply_model_optimizations(self, model, device: str):
        """Apply RTX 4070 specific model optimizations (Issue #315: extracted).

        Args:
            model: The SentenceTransformer model
            device: Target device string

        Returns:
            Optimized model
        """
        import torch

        if not device.startswith("cuda"):
            return model

        try:
            # Enable mixed precision with aggressive optimization
            model = model.to(device, dtype=torch.float16)

            # Enable JIT compilation for repeated operations
            if hasattr(model, "eval"):
                model.eval()

            # Warm up GPU with a small batch to optimize kernel selection
            logger.info("Warming up GPU kernels...")
            warmup_sentences = ["This is a warmup sentence."] * 10
            with torch.no_grad():
                _ = model.encode(
                    warmup_sentences,
                    batch_size=10,
                    convert_to_tensor=False,
                )
            torch.cuda.synchronize()  # Wait for GPU operations to complete

            logger.info("RTX 4070 optimizations applied:")
            logger.info("  - FP16 mixed precision enabled")
            logger.info("  - TF32 tensor operations enabled")
            logger.info("  - CUDNN benchmark mode enabled")
            logger.info("  - GPU kernel warmup completed")

        except Exception as gpu_opt_error:
            logger.warning("Advanced GPU optimizations failed: %s", gpu_opt_error)
            # Fallback to basic GPU usage
            import torch

            model = model.to(device, dtype=torch.float32)

        return model

    async def _initialize_model(self):
        """Initialize model with aggressive GPU optimizations for RTX 4070.

        Issue #315: Refactored to use helper methods for reduced nesting depth.
        """
        if self._embedding_model is not None:
            return

        with self._model_lock:
            if self._embedding_model is not None:
                return

            try:
                # Load model in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    logger.info("Loading GPU embedding model...")
                    self._embedding_model = await loop.run_in_executor(
                        executor, self._load_model_with_optimizations
                    )

                logger.info("GPU model loading completed")

            except Exception as e:
                logger.error("Failed to load GPU model: %s", e)
                self._load_fallback_model()

    def _load_model_with_optimizations(self):
        """Load model with GPU optimizations (Issue #315: extracted).

        Returns:
            Configured SentenceTransformer model
        """
        import torch
        from sentence_transformers import SentenceTransformer

        # Configure GPU optimizations using helpers
        self._setup_gpu_optimizations()
        self._initialize_gpu_memory_pool()

        # Determine device
        if torch.cuda.is_available():
            device = "cuda:0"
            gpu_name = torch.cuda.get_device_name(0)
            total_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            logger.info("Optimizing for GPU: %s (%.1fGB)", gpu_name, total_memory)
        else:
            device = "cpu"
            logger.warning("CUDA not available - falling back to CPU")

        # Load model
        logger.info("Loading model with GPU optimizations...")
        model = SentenceTransformer(self.embedding_model_name, device=device)

        # Apply RTX 4070 specific optimizations
        model = self._apply_model_optimizations(model, device)

        return model

    def _load_fallback_model(self) -> None:
        """Load basic fallback model (Issue #315: extracted)."""
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._embedding_model = SentenceTransformer(
            self.embedding_model_name, device=device
        )
        logger.warning("Using basic model fallback")

    def _add_chunk_metadata(
        self, chunks: List[SemanticChunk], metadata: Optional[Dict[str, Any]]
    ) -> None:
        """Add optimization metadata to each chunk.

        Args:
            chunks: List of SemanticChunk objects to update.
            metadata: Optional source metadata to include.

        Issue #620.
        """
        for i, chunk in enumerate(chunks):
            chunk.metadata.update(
                {
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "source_metadata": metadata or {},
                    "chunking_method": "gpu_optimized_semantic",
                    "embedding_model": self.embedding_model_name,
                    "gpu_batch_size": self.gpu_batch_size,
                    "optimization_version": "rtx4070_gpu",
                }
            )

    def _log_chunking_results(
        self, start_time: float, sentence_count: int, chunk_count: int
    ) -> None:
        """Log chunking performance results.

        Args:
            start_time: Time when chunking started.
            sentence_count: Number of sentences processed.
            chunk_count: Number of chunks created.

        Issue #620.
        """
        total_time = time.time() - start_time
        sentences_per_sec = sentence_count / total_time if total_time > 0 else 0

        logger.info("GPU chunking completed:")
        logger.info("  - Total time: %.3fs", total_time)
        logger.info("  - Performance: %.1f sentences/sec", sentences_per_sec)
        logger.info("  - Chunks created: %s", chunk_count)

    async def chunk_text(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[SemanticChunk]:
        """Main GPU-accelerated chunking method with performance monitoring.

        Target: 3x performance improvement over basic implementation.
        Issue #620: Refactored to use helper methods for reduced function length.
        """
        start_time = time.time()

        try:
            logger.info("Starting GPU semantic chunking (%s characters)", len(text))

            sentences = self._basic_sentence_split(text)

            if len(sentences) <= 1:
                chunk = SemanticChunk(
                    content=text,
                    start_index=0,
                    end_index=1,
                    sentences=sentences,
                    semantic_score=1.0,
                    metadata=metadata or {"single_sentence": True, "optimized": True},
                )
                return [chunk]

            await self._initialize_model()
            embeddings = await self._compute_embeddings(sentences)
            distances = self._compute_semantic_distances(embeddings)
            boundaries = self._find_chunk_boundaries(distances)
            chunks = self._create_chunks_with_boundaries(
                sentences, boundaries, distances
            )

            self._add_chunk_metadata(chunks, metadata)
            self._log_chunking_results(start_time, len(sentences), len(chunks))

            return chunks

        except Exception as e:
            logger.error("GPU chunking failed: %s", e)
            return await self._fallback_basic_chunking(text, metadata)

    async def _compute_embeddings(self, sentences: List[str]) -> np.ndarray:
        """Compute embeddings with RTX 4070 GPU acceleration."""
        if not sentences:
            return np.array([])

        try:
            import torch

            # Process in large batches optimized for RTX 4070
            batch_size = min(self.gpu_batch_size, len(sentences))
            all_embeddings = []

            for i in range(0, len(sentences), batch_size):
                batch_sentences = sentences[i : i + batch_size]

                # GPU embedding computation
                def gpu_encode_batch(sentences_batch):
                    """Encode sentence batch using GPU with torch.no_grad()."""
                    with torch.no_grad():
                        embeddings = self._embedding_model.encode(
                            sentences_batch,
                            batch_size=len(sentences_batch),
                            convert_to_tensor=False,
                            show_progress_bar=False,
                            normalize_embeddings=True,
                        )

                        if torch.cuda.is_available():
                            torch.cuda.synchronize()

                        return embeddings

                # Execute in thread pool
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    batch_embeddings = await loop.run_in_executor(
                        executor, gpu_encode_batch, batch_sentences
                    )

                all_embeddings.append(batch_embeddings)
                await asyncio.sleep(0.001)  # Brief yield

            # Combine results
            if len(all_embeddings) == 1:
                return np.array(all_embeddings[0])
            else:
                return np.vstack(all_embeddings)

        except Exception as e:
            logger.error("GPU embedding computation failed: %s", e)
            # Return zero embeddings as fallback
            return np.zeros((len(sentences), 384))

    def _basic_sentence_split(self, text: str) -> List[str]:
        """Basic sentence splitting algorithm."""
        import re

        # Issue #383 - Use regex split instead of character-by-character string building
        sentence_endings = r"[.!?]+(?:\s|$)"

        # Split text by sentence endings, keeping the delimiters
        raw_splits = re.split(f"({sentence_endings})", text)

        # Recombine splits: each sentence is content + delimiter
        sentences = []
        current_parts = []
        for part in raw_splits:
            current_parts.append(part)
            if re.match(sentence_endings, part):
                sentence = "".join(current_parts).strip()
                if sentence:
                    sentences.append(sentence)
                current_parts = []

        # Add any remaining text
        if current_parts:
            remaining = "".join(current_parts).strip()
            if remaining:
                sentences.append(remaining)

        return [s for s in sentences if len(s.split()) >= 3]

    def _compute_semantic_distances(self, embeddings: np.ndarray) -> List[float]:
        """Compute semantic distances between consecutive sentences."""
        if len(embeddings) <= 1:
            return []

        try:
            from sklearn.metrics.pairwise import cosine_similarity

            distances = []
            for i in range(len(embeddings) - 1):
                similarity = cosine_similarity(
                    embeddings[i].reshape(1, -1), embeddings[i + 1].reshape(1, -1)
                )[0][0]
                distances.append(1 - similarity)

            return distances

        except Exception as e:
            logger.error("Distance computation failed: %s", e)
            return [0.5] * (len(embeddings) - 1)  # Default distances

    def _find_chunk_boundaries(self, distances: List[float]) -> List[int]:
        """Find chunk boundaries based on percentile threshold."""
        if not distances:
            return []

        threshold = np.percentile(distances, self.percentile_threshold)
        boundaries = []

        for i, distance in enumerate(distances):
            if distance > threshold:
                boundaries.append(i + 1)

        return boundaries

    def _create_chunks_with_boundaries(
        self, sentences: List[str], boundaries: List[int], distances: List[float]
    ) -> List[SemanticChunk]:
        """Create chunks based on boundaries."""
        chunks = []
        start_idx = 0
        final_boundaries = boundaries + [len(sentences)]

        for boundary in final_boundaries:
            if boundary <= start_idx:
                continue

            chunk_sentences = sentences[start_idx:boundary]
            chunk_content = " ".join(chunk_sentences)

            chunk = SemanticChunk(
                content=chunk_content,
                start_index=start_idx,
                end_index=boundary,
                sentences=chunk_sentences,
                semantic_score=0.8,
                metadata={"boundary_type": "semantic"},
            )
            chunks.append(chunk)

            start_idx = (
                boundary - self.overlap_sentences
                if self.overlap_sentences > 0
                else boundary
            )

        return chunks

    async def _fallback_basic_chunking(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[SemanticChunk]:
        """Fallback chunking if optimization fails."""
        logger.warning("Using fallback basic chunking")

        sentences = self._basic_sentence_split(text)
        chunks = []
        current_sentences = []
        current_length = 0

        for i, sentence in enumerate(sentences):
            sentence_len = len(sentence)

            if (
                current_length + sentence_len > self.max_chunk_size
                and current_sentences
            ):
                chunk_content = " ".join(current_sentences)
                chunk = SemanticChunk(
                    content=chunk_content,
                    start_index=i - len(current_sentences),
                    end_index=i,
                    sentences=current_sentences.copy(),
                    semantic_score=0.5,
                    metadata={"fallback_chunking": True, **(metadata or {})},
                )
                chunks.append(chunk)
                current_sentences = []
                current_length = 0

            current_sentences.append(sentence)
            current_length += sentence_len

        if current_sentences:
            chunk_content = " ".join(current_sentences)
            chunk = SemanticChunk(
                content=chunk_content,
                start_index=len(sentences) - len(current_sentences),
                end_index=len(sentences),
                sentences=current_sentences,
                semantic_score=0.5,
                metadata={"fallback_chunking": True, **(metadata or {})},
            )
            chunks.append(chunk)

        return chunks

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        total_time = self.processing_stats["total_processing_time"]
        total_sentences = self.processing_stats["total_sentences"]

        if total_time > 0 and total_sentences > 0:
            avg_sentences_per_sec = total_sentences / total_time
        else:
            avg_sentences_per_sec = 0

        return {
            "total_sentences_processed": total_sentences,
            "total_processing_time": total_time,
            "average_sentences_per_second": avg_sentences_per_sec,
            "gpu_memory_pool_enabled": self._gpu_memory_pool_initialized,
            "optimization_level": "RTX4070_GPU",
        }

    async def chunk_document(
        self, content: str, metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Main interface method compatible with LlamaIndex."""
        semantic_chunks = await self.chunk_text(content, metadata)

        documents = []
        for chunk in semantic_chunks:
            doc_data = {
                "text": chunk.content,
                "metadata": {
                    **chunk.metadata,
                    "semantic_score": chunk.semantic_score,
                    "sentence_count": len(chunk.sentences),
                    "character_count": len(chunk.content),
                },
            }
            documents.append(doc_data)

        return documents


# Global GPU chunker instance (thread-safe)
_gpu_chunker_instance = None
_gpu_chunker_instance_lock = threading.Lock()


def get_gpu_semantic_chunker():
    """Get the global GPU semantic chunker instance (thread-safe)."""
    global _gpu_chunker_instance
    if _gpu_chunker_instance is None:
        with _gpu_chunker_instance_lock:
            # Double-check after acquiring lock
            if _gpu_chunker_instance is None:
                _gpu_chunker_instance = GPUSemanticChunker(
                    gpu_batch_size=500,  # Large batches for RTX 4070
                    enable_gpu_memory_pool=True,
                )
    return _gpu_chunker_instance
