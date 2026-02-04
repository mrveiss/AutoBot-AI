# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Semantic Chunking Module

Implements advanced semantic chunking to replace basic sentence splitting.
Uses percentile-based semantic distance thresholds for intelligent document
segmentation.
"""

import os

# CRITICAL FIX: Force tf-keras usage before importing transformers/sentence-transformers
os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ["KERAS_BACKEND"] = "tensorflow"

# Reduce Hugging Face rate limiting and improve caching
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "0"  # Allow downloads but cache aggressively
os.environ["HF_HUB_CACHE"] = os.path.expanduser("~/.cache/huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.expanduser("~/.cache/huggingface")

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

# Import centralized logging
from src.constants.threshold_constants import RetryConfig, TimingConstants
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("semantic_chunker")

# Issue #380: Pre-compiled regex patterns for sentence splitting
_SENTENCE_ENDINGS_RE = re.compile(r"([.!?]+(?:\s|$))")
_SENTENCE_ENDING_MATCH_RE = re.compile(r"[.!?]+(?:\s|$)")
_ABBREVIATIONS_RE = re.compile(
    r"(?:Mr|Mrs|Dr|Prof|Sr|Jr|vs|etc|Inc|Ltd|Corp|Co|St|Ave|Rd|Blvd|"
    r"Apt|No|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Mon|Tue|"
    r"Wed|Thu|Fri|Sat|Sun)\.(?!\s*$)"
)


@dataclass
class SemanticChunk:
    """Represents a semantically coherent chunk of text."""

    content: str
    start_index: int
    end_index: int
    sentences: List[str]
    semantic_score: float
    metadata: Dict[str, Any]


class AutoBotSemanticChunker:
    """
    Advanced semantic chunking implementation for AutoBot.

    Uses sentence-transformer embeddings and percentile-based thresholding
    to create semantically coherent chunks that maintain contextual
    relationships.
    """

    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        percentile_threshold: float = 95.0,
        min_chunk_size: int = 100,
        max_chunk_size: int = 1000,
        overlap_sentences: int = 1,
    ):
        """
        Initialize the semantic chunker.

        Args:
            embedding_model: SentenceTransformer model name
            percentile_threshold: Percentile threshold for semantic breaks
                (95th percentile)
            min_chunk_size: Minimum characters per chunk
            max_chunk_size: Maximum characters per chunk
            overlap_sentences: Number of sentences to overlap between
                chunks
        """
        self.embedding_model_name = embedding_model
        self.percentile_threshold = percentile_threshold
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_sentences = overlap_sentences

        # Initialize embedding model placeholder - will be loaded lazily
        self._embedding_model = None

        logger.info("SemanticChunker initialized with model: %s", embedding_model)

    def _check_gpu_availability(self) -> bool:
        """Issue #665: Extracted from _compute_sentence_embeddings_async to reduce function length."""
        import torch

        return (
            torch.cuda.is_available()
            and hasattr(self, "_embedding_model")
            and self._embedding_model is not None
            and next(self._embedding_model.parameters()).device.type == "cuda"
        )

    def _get_system_info_for_batching(self) -> tuple[int, float, bool]:
        """Issue #665: Extracted from _compute_sentence_embeddings_async to reduce function length."""
        import os

        import psutil

        cpu_count = os.cpu_count() or 4
        cpu_load = psutil.cpu_percent(interval=0.1)
        has_gpu = self._check_gpu_availability()
        return cpu_count, cpu_load, has_gpu

    async def _process_embedding_batches(
        self, sentences: List[str], batch_size: int, max_workers: int
    ) -> List[np.ndarray]:
        """Issue #665: Extracted from _compute_sentence_embeddings_async to reduce function length.

        Process sentences in batches and return list of embedding arrays.

        Args:
            sentences: List of sentence strings to embed.
            batch_size: Number of sentences per batch.
            max_workers: Maximum number of worker threads.

        Returns:
            List of numpy arrays containing embeddings for each batch.
        """
        import asyncio
        import concurrent.futures

        all_embeddings = []

        for i in range(0, len(sentences), batch_size):
            batch_sentences = sentences[i : i + batch_size]

            # Run embedding computation in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers
            ) as executor:
                embeddings = await loop.run_in_executor(
                    executor,
                    lambda: self._embedding_model.encode(
                        batch_sentences,
                        convert_to_tensor=False,
                        show_progress_bar=False,
                    ),
                )
                all_embeddings.append(embeddings)

            # Yield control to event loop after each batch
            await asyncio.sleep(0.001)  # Allow other coroutines to run

            # Log progress for large batches
            if len(sentences) > 20:
                progress = min(100, int((i + batch_size) / len(sentences) * 100))
                logger.debug("Embedding progress: %d%%", progress)

        return all_embeddings

    def _create_fallback_embeddings(self, num_sentences: int) -> np.ndarray:
        """Issue #665: Extracted from _compute_sentence_embeddings_async to reduce function length.

        Create zero embeddings as fallback when embedding computation fails.

        Args:
            num_sentences: Number of sentences to create embeddings for.

        Returns:
            numpy array of zero embeddings with appropriate dimensions.
        """
        try:
            dim = self._embedding_model.get_sentence_embedding_dimension()
            return np.zeros((num_sentences, dim))
        except Exception:
            # Fallback dimension if model access fails
            return np.zeros((num_sentences, 384))

    def _get_adaptive_batch_params(
        self, num_sentences: int, cpu_load: float, cpu_count: int, has_gpu: bool
    ) -> tuple[int, int]:
        """
        Determine adaptive batch size and worker count based on system load.

        Issue #281: Extracted helper to reduce repetition in _compute_sentence_embeddings_async.

        Args:
            num_sentences: Total number of sentences to process
            cpu_load: Current CPU load percentage
            cpu_count: Number of available CPU cores
            has_gpu: Whether GPU acceleration is available

        Returns:
            Tuple of (max_workers, batch_size)
        """
        if has_gpu:
            # GPU mode: Use larger batches and more CPU workers for preprocessing
            if cpu_load > 80:
                max_workers = min(4, cpu_count // 4)  # Still use multiple workers
                batch_size = min(50, num_sentences)  # Larger batches for GPU
            elif cpu_load > 50:
                max_workers = min(8, cpu_count // 2)  # More workers available
                batch_size = min(100, num_sentences)  # Bigger batches
            else:
                # Low CPU load: maximize parallel processing
                max_workers = min(12, cpu_count)  # Use more of your 22 cores
                batch_size = min(200, num_sentences)  # Large GPU batches
        else:
            # CPU-only mode: More conservative batching
            if cpu_load > 80:
                max_workers = min(2, cpu_count // 8)
                batch_size = min(10, num_sentences)
            elif cpu_load > 50:
                max_workers = min(4, cpu_count // 4)
                batch_size = min(25, num_sentences)
            else:
                max_workers = min(6, cpu_count // 2)  # Still use good parallelism
                batch_size = min(50, num_sentences)

        return max_workers, batch_size

    def _detect_device(self):
        """Detect best available device for model loading (Issue #333 - extracted helper)."""
        import torch

        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            gpu_name = torch.cuda.get_device_name(0) if gpu_count > 0 else "Unknown"
            logger.info("Using CUDA GPU: %s (device count: %d)", gpu_name, gpu_count)
            return "cuda"

        logger.info("CUDA not available, using CPU for embeddings")
        return "cpu"

    def _apply_gpu_precision(self, model, device: str):
        """Apply GPU precision optimization to model (Issue #333 - extracted helper)."""
        import torch

        if device != "cuda":
            return model

        try:
            param_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
            if param_count == 0:
                logger.warning(
                    "Model parameters not properly loaded, skipping precision conversion"
                )
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
        """Load model with retry logic for rate limiting (Issue #333 - extracted helper)."""
        import time

        from sentence_transformers import SentenceTransformer

        max_retries = RetryConfig.DEFAULT_RETRIES
        retry_delay = TimingConstants.SERVICE_STARTUP_DELAY

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(
                        f"Model loading attempt {attempt + 1}/{max_retries} after {retry_delay}s delay..."
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2

                return SentenceTransformer(self.embedding_model_name, device=device)

            except Exception as load_error:
                error_str = str(load_error).lower()
                is_rate_limit = (
                    "429" in error_str
                    or "rate limit" in error_str
                    or "http error" in error_str
                )

                if not is_rate_limit:
                    raise

                if attempt >= max_retries - 1:
                    logger.error(
                        "Max retries exceeded for HuggingFace rate limiting: %s",
                        load_error,
                    )
                    raise

                logger.warning(
                    "HuggingFace rate limit hit (attempt %d), retrying in %ds...",
                    attempt + 1,
                    retry_delay,
                )

        raise RuntimeError("Model loading failed after retries")

    def _optimize_loaded_model(self, model, device: str):
        """Optimize loaded model for device (Issue #333 - extracted helper)."""
        from sentence_transformers import SentenceTransformer

        try:
            actual_device = next(model.parameters()).device
            logger.info(
                "Embedding model '%s' loaded on device: %s",
                self.embedding_model_name,
                actual_device,
            )

            model = self._apply_gpu_precision(model, device)
            return model

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

    async def _initialize_model(self):
        """Lazy initialize the sentence transformer model on first use with GPU acceleration."""
        if self._embedding_model is not None:
            return

        try:
            import asyncio
            import concurrent.futures

            def load_model():
                """Load and optimize embedding model on detected device."""
                device = self._detect_device()
                model = self._load_model_with_retry(device)
                return self._optimize_loaded_model(model, device)

            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                logger.info(
                    "Loading embedding model '%s' in background thread...",
                    self.embedding_model_name,
                )
                self._embedding_model = await loop.run_in_executor(executor, load_model)
                logger.info("Embedding model loading completed")

        except Exception as e:
            logger.error(
                "Failed to load embedding model %s: %s", self.embedding_model_name, e
            )
            await self._try_fallback_models()

    async def _try_fallback_models(self):
        """Try loading fallback models (Issue #333 - extracted helper)."""
        from sentence_transformers import SentenceTransformer

        fallback_models = ["all-mpnet-base-v2", "all-MiniLM-L12-v2"]

        for model_name in fallback_models:
            try:
                logger.info("Attempting fallback model loading on CPU: %s", model_name)
                self._embedding_model = SentenceTransformer(model_name)
                logger.warning("Fallback to %s embedding model on CPU", model_name)
                return
            except Exception as fallback_error:
                logger.error(
                    "Failed to load fallback model %s: %s", model_name, fallback_error
                )

        raise RuntimeError("Could not initialize any embedding model")

    def _sync_try_fallback_models(self, device: str):
        """Try loading fallback models synchronously (Issue #333 - extracted helper)."""
        from sentence_transformers import SentenceTransformer

        self._embedding_model = SentenceTransformer("all-mpnet-base-v2")

        if device == "cuda":
            try:
                has_meta_tensors = any(
                    p.device.type == "meta" for p in self._embedding_model.parameters()
                )
                if has_meta_tensors:
                    self._embedding_model = self._embedding_model.to_empty(
                        device=device
                    )
                else:
                    self._embedding_model = self._embedding_model.to(device)
            except Exception as device_error:
                logger.warning(
                    "Failed to move model to GPU: %s, using CPU", device_error
                )
                device = "cpu"

        logger.warning("Fallback to all-mpnet-base-v2 embedding model on %s", device)

    def _sync_initialize_model(self):
        """Synchronous model initialization for fallback cases (blocking)."""
        if self._embedding_model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            device = self._detect_device()
            self._embedding_model = SentenceTransformer(
                self.embedding_model_name, device=device
            )

            actual_device = next(self._embedding_model.parameters()).device
            logger.info(
                "Embedding model '%s' loaded on device: %s",
                self.embedding_model_name,
                actual_device,
            )

            self._embedding_model = self._apply_gpu_precision(
                self._embedding_model, device
            )

        except Exception as e:
            logger.error(
                "Failed to load embedding model %s: %s", self.embedding_model_name, e
            )
            try:
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
                self._sync_try_fallback_models(device)
            except Exception as fallback_error:
                logger.error("Failed to load fallback model: %s", fallback_error)
                raise RuntimeError("Could not initialize any embedding model")

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using improved sentence boundary detection.

        Args:
            text: Input text to split

        Returns:
            List of sentence strings
        """
        # Issue #383 - Use regex split instead of character-by-character string building
        # Issue #380 - Use pre-compiled patterns from module level
        # Split text by sentence endings, keeping the delimiters
        raw_splits = _SENTENCE_ENDINGS_RE.split(text)

        # Recombine splits: each sentence is content + delimiter
        sentences = []
        current_sentence = ""
        for i, part in enumerate(raw_splits):
            current_sentence += part
            # Check if this part is a sentence ending (odd indices after split with group)
            if _SENTENCE_ENDING_MATCH_RE.match(part):
                # Check if this is likely an abbreviation
                if not _ABBREVIATIONS_RE.search(current_sentence):
                    stripped = current_sentence.strip()
                    if stripped:
                        sentences.append(stripped)
                    current_sentence = ""

        # Add any remaining text as a sentence
        if current_sentence.strip():
            sentences.append(current_sentence.strip())

        # Filter out very short sentences (likely parsing errors)
        sentences = [s for s in sentences if len(s.split()) >= 3]

        return sentences

    async def _compute_sentence_embeddings_async(
        self, sentences: List[str]
    ) -> np.ndarray:
        """Compute embeddings for sentences asynchronously (Issue #665: refactored to <50 lines)."""
        # Ensure model is loaded before use
        await self._initialize_model()

        try:
            # Get system info using extracted helper (Issue #665)
            cpu_count, cpu_load, has_gpu = self._get_system_info_for_batching()

            # Get adaptive batch parameters (Issue #281)
            max_workers, batch_size = self._get_adaptive_batch_params(
                len(sentences), cpu_load, cpu_count, has_gpu
            )

            logger.info(
                f"Processing {len(sentences)} sentences with {max_workers} workers, "
                f"batch_size={batch_size}, CPU load={cpu_load}%"
            )

            # Process batches using extracted helper (Issue #665)
            all_embeddings = await self._process_embedding_batches(
                sentences, batch_size, max_workers
            )

            # Combine all batch results
            if len(all_embeddings) == 1:
                return np.array(all_embeddings[0])
            return np.vstack(all_embeddings)

        except Exception as e:
            logger.error("Error computing sentence embeddings: %s", e)
            return self._create_fallback_embeddings(len(sentences))

    def _compute_sentence_embeddings(self, sentences: List[str]) -> np.ndarray:
        """
        Synchronous wrapper for backward compatibility.

        Args:
            sentences: List of sentence strings

        Returns:
            numpy array of embeddings
        """
        import asyncio

        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, we shouldn't use this sync method
                logger.warning(
                    "Using sync embedding method in async context. "
                    "Use _compute_sentence_embeddings_async instead."
                )
                logger.warning(
                    "WARNING: Model initialization may block event loop - use async method instead"
                )
                # Fall back to direct computation (blocking) - creates a new sync version for
                # fallback
                if self._embedding_model is None:
                    self._sync_initialize_model()
                embeddings = self._embedding_model.encode(
                    sentences, convert_to_tensor=False
                )
                return np.array(embeddings)
            else:
                # Run the async version
                return loop.run_until_complete(
                    self._compute_sentence_embeddings_async(sentences)
                )
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self._compute_sentence_embeddings_async(sentences))

    def _compute_semantic_distances(self, embeddings: np.ndarray) -> List[float]:
        """
        Compute semantic distances between consecutive sentences.

        Args:
            embeddings: Array of sentence embeddings

        Returns:
            List of cosine distances between consecutive sentences
        """
        if len(embeddings) <= 1:
            return []

        from sklearn.metrics.pairwise import cosine_similarity

        distances = []
        for i in range(len(embeddings) - 1):
            # Compute cosine similarity between consecutive sentences
            similarity = cosine_similarity(
                embeddings[i].reshape(1, -1), embeddings[i + 1].reshape(1, -1)
            )[0][0]
            # Convert similarity to distance
            distance = 1 - similarity
            distances.append(distance)

        return distances

    def _find_chunk_boundaries(self, distances: List[float]) -> List[int]:
        """
        Find chunk boundaries based on percentile threshold.

        Args:
            distances: List of semantic distances between sentences

        Returns:
            List of sentence indices where chunks should split
        """
        if not distances:
            return []

        # Calculate percentile threshold
        threshold = np.percentile(distances, self.percentile_threshold)

        boundaries = []
        for i, distance in enumerate(distances):
            if distance > threshold:
                # +1 because distance[i] is between sentence i and i+1
                boundaries.append(i + 1)

        return boundaries

    def _merge_with_previous_chunk(
        self, chunks: List[SemanticChunk], chunk_sentences: List[str], boundary: int
    ) -> None:
        """Merge small chunk with previous chunk. Issue #620."""
        prev_chunk = chunks[-1]
        merged_sentences = prev_chunk.sentences + chunk_sentences
        merged_content = " ".join(merged_sentences)
        chunks[-1] = SemanticChunk(
            content=merged_content,
            start_index=prev_chunk.start_index,
            end_index=boundary,
            sentences=merged_sentences,
            semantic_score=0.8,
            metadata={"merged": True, "original_boundary": boundary},
        )

    def _create_regular_chunk(
        self,
        chunk_content: str,
        chunk_sentences: List[str],
        start_idx: int,
        boundary: int,
    ) -> SemanticChunk:
        """Create a regular semantic chunk. Issue #620."""
        return SemanticChunk(
            content=chunk_content,
            start_index=start_idx,
            end_index=boundary,
            sentences=chunk_sentences,
            semantic_score=0.8,
            metadata={"boundary_type": "semantic"},
        )

    def _create_chunks_with_boundaries(
        self, sentences: List[str], boundaries: List[int], distances: List[float]
    ) -> List[SemanticChunk]:
        """Create semantic chunks based on identified boundaries. Issue #620: Refactored."""
        chunks = []
        start_idx = 0
        final_boundaries = boundaries + [len(sentences)]

        for boundary in final_boundaries:
            if boundary <= start_idx:
                continue

            chunk_sentences = sentences[start_idx:boundary]
            chunk_content = " ".join(chunk_sentences)

            if len(chunk_content) < self.min_chunk_size and chunks:
                self._merge_with_previous_chunk(chunks, chunk_sentences, boundary)
            elif len(chunk_content) > self.max_chunk_size:
                chunks.extend(self._split_large_chunk(chunk_sentences, start_idx))
            else:
                chunks.append(
                    self._create_regular_chunk(
                        chunk_content, chunk_sentences, start_idx, boundary
                    )
                )

            start_idx = (
                boundary - self.overlap_sentences
                if self.overlap_sentences > 0
                else boundary
            )

        return chunks

    def _split_large_chunk(
        self, sentences: List[str], start_idx: int
    ) -> List[SemanticChunk]:
        """
        Split a chunk that exceeds maximum size into smaller chunks.

        Args:
            sentences: Sentences in the large chunk
            start_idx: Starting index for sentence numbering

        Returns:
            List of smaller semantic chunks
        """
        chunks = []
        current_sentences = []
        current_length = 0
        sentence_idx = start_idx

        for sentence in sentences:
            sentence_len = len(sentence)

            if (
                current_length + sentence_len > self.max_chunk_size
                and current_sentences
            ):
                # Create chunk from current sentences
                chunk_content = " ".join(current_sentences)
                chunk = SemanticChunk(
                    content=chunk_content,
                    start_index=sentence_idx - len(current_sentences),
                    end_index=sentence_idx,
                    sentences=current_sentences.copy(),
                    semantic_score=0.7,  # Default coherence for size-constrained chunks
                    metadata={"split_type": "size_constraint"},
                )
                chunks.append(chunk)

                # Reset for next chunk with overlap
                if self.overlap_sentences > 0:
                    overlap_start = -self.overlap_sentences
                    current_sentences = current_sentences[overlap_start:]
                    current_length = sum(len(s) for s in current_sentences)
                else:
                    current_sentences = []
                    current_length = 0

            current_sentences.append(sentence)
            current_length += sentence_len
            sentence_idx += 1

        # Add final chunk if there are remaining sentences
        if current_sentences:
            chunk_content = " ".join(current_sentences)
            chunk = SemanticChunk(
                content=chunk_content,
                start_index=sentence_idx - len(current_sentences),
                end_index=sentence_idx,
                sentences=current_sentences,
                semantic_score=0.7,  # Default coherence for final size-constrained chunks
                metadata={"split_type": "size_constraint", "final_chunk": True},
            )
            chunks.append(chunk)

        return chunks

    async def _calculate_chunk_coherence_async(self, sentences: List[str]) -> float:
        """
        Calculate semantic coherence score for a chunk.

        Args:
            sentences: List of sentences in the chunk

        Returns:
            Coherence score (0-1, higher is more coherent)
        """
        if len(sentences) <= 1:
            return 1.0

        try:
            embeddings = await self._compute_sentence_embeddings_async(sentences)
            if len(embeddings) <= 1:
                return 1.0

            from sklearn.metrics.pairwise import cosine_similarity

            # Calculate average pairwise similarity within the chunk
            similarities = []
            for i in range(len(embeddings)):
                for j in range(i + 1, len(embeddings)):
                    similarity = cosine_similarity(
                        embeddings[i].reshape(1, -1), embeddings[j].reshape(1, -1)
                    )[0][0]
                    similarities.append(similarity)

            return np.mean(similarities) if similarities else 1.0
        except Exception as e:
            logger.error("Error calculating chunk coherence: %s", e)
            return 0.5  # Default neutral score

    def _create_single_sentence_chunk(
        self, text: str, sentences: List[str], metadata: Optional[Dict[str, Any]]
    ) -> SemanticChunk:
        """
        Create a chunk for single-sentence or empty text. Issue #620.

        Args:
            text: Original input text
            sentences: List of sentences (0 or 1 item)
            metadata: Optional metadata to attach

        Returns:
            SemanticChunk for the single sentence
        """
        return SemanticChunk(
            content=text,
            start_index=0,
            end_index=1,
            sentences=sentences,
            semantic_score=1.0,
            metadata=metadata or {"single_sentence": True},
        )

    def _enrich_chunks_with_metadata(
        self, chunks: List[SemanticChunk], metadata: Optional[Dict[str, Any]]
    ) -> None:
        """
        Add metadata to all chunks including index and model info. Issue #620.

        Args:
            chunks: List of chunks to enrich
            metadata: Source metadata to include
        """
        for i, chunk in enumerate(chunks):
            chunk.metadata.update(
                {
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "source_metadata": metadata or {},
                    "chunking_method": "semantic_percentile",
                    "embedding_model": self.embedding_model_name,
                    "percentile_threshold": self.percentile_threshold,
                }
            )

    async def chunk_text(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[SemanticChunk]:
        """
        Chunk text using semantic analysis. Issue #620: Refactored with helpers.

        Args:
            text: Input text to chunk
            metadata: Optional metadata to attach to chunks

        Returns:
            List of SemanticChunk objects
        """
        try:
            logger.info("Starting semantic chunking of text (%d characters)", len(text))

            sentences = self._split_into_sentences(text)
            if len(sentences) <= 1:
                return [self._create_single_sentence_chunk(text, sentences, metadata)]

            logger.debug("Split text into %d sentences", len(sentences))

            embeddings = await self._compute_sentence_embeddings_async(sentences)
            distances = self._compute_semantic_distances(embeddings)
            boundaries = self._find_chunk_boundaries(distances)

            logger.debug("Found %d semantic boundaries", len(boundaries))

            chunks = self._create_chunks_with_boundaries(
                sentences, boundaries, distances
            )
            self._enrich_chunks_with_metadata(chunks, metadata)

            avg_coherence = np.mean([c.semantic_score for c in chunks])
            logger.info(
                "Created %d semantic chunks with average coherence: %.3f",
                len(chunks),
                avg_coherence,
            )

            return chunks

        except Exception as e:
            logger.error("Error in semantic chunking: %s", e)
            return await self._fallback_chunking(text, metadata)

    async def _fallback_chunking(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[SemanticChunk]:
        """
        Fallback chunking method when semantic analysis fails.

        Args:
            text: Input text
            metadata: Optional metadata

        Returns:
            List of basic chunks
        """
        logger.warning("Using fallback chunking method")

        # Simple sentence-based chunking
        sentences = self._split_into_sentences(text)
        chunks = []

        current_sentences = []
        current_length = 0

        for i, sentence in enumerate(sentences):
            sentence_len = len(sentence)

            if (
                current_length + sentence_len > self.max_chunk_size
                and current_sentences
            ):
                # Create chunk
                chunk_content = " ".join(current_sentences)
                chunk = SemanticChunk(
                    content=chunk_content,
                    start_index=i - len(current_sentences),
                    end_index=i,
                    sentences=current_sentences.copy(),
                    semantic_score=0.5,  # Default score
                    metadata={"fallback_chunking": True, **(metadata or {})},
                )
                chunks.append(chunk)
                current_sentences = []
                current_length = 0

            current_sentences.append(sentence)
            current_length += sentence_len

        # Add final chunk
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

    async def chunk_document(
        self, content: str, metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Main interface method compatible with LlamaIndex Document format.

        Args:
            content: Document content text
            metadata: Document metadata

        Returns:
            List of chunk dictionaries compatible with LlamaIndex
        """
        semantic_chunks = await self.chunk_text(content, metadata)

        # Convert to LlamaIndex-compatible format
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


# Global instance placeholder - will be created lazily (thread-safe)
import threading

_semantic_chunker_instance = None
_semantic_chunker_instance_lock = threading.Lock()


def get_semantic_chunker():
    """Get the global semantic chunker instance (lazy initialization, thread-safe)."""
    global _semantic_chunker_instance
    if _semantic_chunker_instance is None:
        with _semantic_chunker_instance_lock:
            # Double-check after acquiring lock
            if _semantic_chunker_instance is None:
                _semantic_chunker_instance = AutoBotSemanticChunker()
    return _semantic_chunker_instance
