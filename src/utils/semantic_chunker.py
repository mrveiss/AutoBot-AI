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

from src.constants.network_constants import NetworkConstants

# CRITICAL FIX: Force tf-keras usage before importing transformers/sentence-transformers
os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ["KERAS_BACKEND"] = "tensorflow"

# Reduce Hugging Face rate limiting and improve caching
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "0"  # Allow downloads but cache aggressively
os.environ["HF_HUB_CACHE"] = os.path.expanduser("~/.cache/huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.expanduser("~/.cache/huggingface")

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

# Import centralized logging
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("semantic_chunker")


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

        logger.info(f"SemanticChunker initialized with model: {embedding_model}")

    async def _initialize_model(self):
        """Lazy initialize the sentence transformer model on first use with GPU acceleration."""
        if self._embedding_model is not None:
            return

        try:
            import asyncio
            import concurrent.futures

            # Run model loading in thread pool to avoid blocking event loop
            def load_model():
                # Import only when needed to avoid startup delay
                import time

                import torch
                from sentence_transformers import SentenceTransformer

                # Detect best available device
                device = "cpu"  # Default fallback

                if torch.cuda.is_available():
                    device = "cuda"
                    gpu_count = torch.cuda.device_count()
                    gpu_name = (
                        torch.cuda.get_device_name(0) if gpu_count > 0 else "Unknown"
                    )
                    logger.info(
                        f"Using CUDA GPU: {gpu_name} (device count: {gpu_count})"
                    )
                else:
                    logger.info("CUDA not available, using CPU for embeddings")

                # Initialize model with device optimization and retry logic for
                # HuggingFace rate limiting
                max_retries = 3
                retry_delay = 2  # seconds

                for attempt in range(max_retries):
                    try:
                        if attempt > 0:
                            logger.info(
                                f"Model loading attempt {attempt + 1}/{max_retries} after {retry_delay}s delay..."
                            )
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff

                        # Try to load model (this may hit HuggingFace rate limits)
                        model = SentenceTransformer(
                            self.embedding_model_name, device=device
                        )
                        break  # Success - exit retry loop

                    except Exception as load_error:
                        error_str = str(load_error).lower()
                        if (
                            "429" in error_str
                            or "rate limit" in error_str
                            or "http error" in error_str
                        ):
                            if attempt < max_retries - 1:
                                logger.warning(
                                    f"HuggingFace rate limit hit (attempt {attempt + 1}), retrying in {retry_delay}s..."
                                )
                                continue
                            else:
                                logger.error(
                                    f"Max retries exceeded for HuggingFace rate limiting: {load_error}"
                                )
                                raise
                        else:
                            # Non-rate-limit error, don't retry
                            raise

                # After successful model loading, try to optimize for GPU
                try:
                    # Log device and model info
                    actual_device = next(model.parameters()).device
                    logger.info(
                        f"Embedding model '{self.embedding_model_name}' loaded on device: {actual_device}"
                    )

                    # Enable mixed precision for GPU if available (with proper error handling)
                    if device == "cuda":
                        try:
                            # Check if model parameters are properly loaded before precision
                            # conversion
                            param_count = sum(
                                p.numel() for p in model.parameters() if p.requires_grad
                            )
                            if param_count > 0:
                                # Use safe tensor conversion for meta tensors
                                try:
                                    # First check if any parameters are on meta device
                                    has_meta_tensors = any(
                                        p.device.type == "meta"
                                        for p in model.parameters()
                                    )
                                    if has_meta_tensors:
                                        # Use to_empty() for meta tensors
                                        model = model.to_empty(
                                            device=device, dtype=torch.float16
                                        )
                                        logger.info(
                                            "Converted meta tensors to FP16 on GPU"
                                        )
                                    else:
                                        # Use regular to() for normal tensors
                                        model = model.to(device, dtype=torch.float16)
                                        logger.info(
                                            "Enabled FP16 mixed precision for GPU inference"
                                        )
                                except Exception as tensor_error:
                                    logger.warning(
                                        f"FP16 conversion failed: {tensor_error}, trying FP32"
                                    ),
                                    model = model.to(device, dtype=torch.float32)
                            else:
                                logger.warning(
                                    "Model parameters not properly loaded, skipping precision conversion"
                                )
                        except Exception as precision_error:
                            logger.warning(
                                f"Could not enable FP16: {precision_error}, using FP32"
                            )
                            # Ensure model is on correct device even if precision fails
                            model = model.to(device)

                except Exception as model_load_error:
                    logger.warning(
                        f"Failed to load model '{self.embedding_model_name}' on {device}: {model_load_error}"
                    )
                    # Fallback to CPU with basic loading
                    if device != "cpu":
                        logger.info("Attempting fallback to CPU...")
                        model = SentenceTransformer(
                            self.embedding_model_name, device="cpu"
                        )
                    else:
                        raise  # Re-raise if CPU also fails

                return model

            # Load model in background thread
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                logger.info(
                    f"Loading embedding model '{self.embedding_model_name}' in background thread..."
                )
                self._embedding_model = await loop.run_in_executor(executor, load_model)
                logger.info("Embedding model loading completed")

        except Exception as e:
            logger.error(
                f"Failed to load embedding model {self.embedding_model_name}: {e}"
            )
            # Fallback to a more basic model with safer loading
            try:
                import torch
                from sentence_transformers import SentenceTransformer

                # Use CPU only for fallback to avoid device/tensor issues
                logger.info(
                    "Attempting fallback model loading on CPU to avoid tensor issues..."
                )
                self._embedding_model = SentenceTransformer("all-mpnet-base-v2")
                logger.warning("Fallback to all-mpnet-base-v2 embedding model on CPU")
            except Exception as fallback_error:
                logger.error(f"Failed to load fallback model: {fallback_error}")
                # Try one more fallback with a very simple model
                try:
                    # Use the simplest possible model with CPU only
                    self._embedding_model = SentenceTransformer("all-MiniLM-L12-v2")
                    logger.warning("Using basic CPU-only model as final fallback")
                except Exception as final_error:
                    logger.error(f"All model loading attempts failed: {final_error}")
                    raise RuntimeError("Could not initialize any embedding model")

    def _sync_initialize_model(self):
        """Synchronous model initialization for fallback cases (blocking)."""
        if self._embedding_model is not None:
            return

        try:
            # Import only when needed to avoid startup delay
            import torch
            from sentence_transformers import SentenceTransformer

            # Detect best available device
            device = "cpu"  # Default fallback

            if torch.cuda.is_available():
                device = "cuda"
                gpu_count = torch.cuda.device_count()
                gpu_name = torch.cuda.get_device_name(0) if gpu_count > 0 else "Unknown"
                logger.info(f"Using CUDA GPU: {gpu_name} (device count: {gpu_count})")
            else:
                logger.info("CUDA not available, using CPU for embeddings")

            # Initialize model with device optimization
            self._embedding_model = SentenceTransformer(
                self.embedding_model_name, device=device
            )

            # Log device and model info
            actual_device = next(self._embedding_model.parameters()).device
            logger.info(
                f"Embedding model '{self.embedding_model_name}' loaded on device: {actual_device}"
            )

            # Enable mixed precision for GPU if available
            if device == "cuda":
                try:
                    # Safe tensor conversion for mixed precision
                    has_meta_tensors = any(
                        p.device.type == "meta"
                        for p in self._embedding_model.parameters()
                    )
                    if has_meta_tensors:
                        # Use to_empty() for meta tensors
                        self._embedding_model = self._embedding_model.to_empty(
                            device=device, dtype=torch.float16
                        )
                        logger.info("Converted meta tensors to FP16 on GPU")
                    else:
                        # Use regular to() for normal tensors
                        self._embedding_model = self._embedding_model.to(
                            device, dtype=torch.float16
                        )
                        logger.info("Enabled FP16 mixed precision for GPU inference")
                except Exception as precision_error:
                    logger.warning(
                        f"Could not enable FP16: {precision_error}, using FP32"
                    )
                    # Ensure model is on correct device
                    self._embedding_model = self._embedding_model.to(
                        device, dtype=torch.float32
                    )

        except Exception as e:
            logger.error(
                f"Failed to load embedding model {self.embedding_model_name}: {e}"
            )
            # Fallback to a more basic model
            try:
                import torch
                from sentence_transformers import SentenceTransformer

                device = "cuda" if torch.cuda.is_available() else "cpu"
                # Load model without specifying device to avoid meta tensor issues
                self._embedding_model = SentenceTransformer("all-mpnet-base-v2")
                # Then manually move to device with proper handling
                if device == "cuda":
                    try:
                        has_meta_tensors = any(
                            p.device.type == "meta"
                            for p in self._embedding_model.parameters()
                        )
                        if has_meta_tensors:
                            self._embedding_model = self._embedding_model.to_empty(
                                device=device
                            )
                        else:
                            self._embedding_model = self._embedding_model.to(device)
                    except Exception as device_error:
                        logger.warning(
                            f"Failed to move model to GPU: {device_error}, using CPU"
                        ),
                        device = "cpu"
                logger.warning(
                    f"Fallback to all-mpnet-base-v2 embedding model on {device}"
                )
            except Exception as fallback_error:
                logger.error(f"Failed to load fallback model: {fallback_error}")
                raise RuntimeError("Could not initialize any embedding model")

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using improved sentence boundary detection.

        Args:
            text: Input text to split

        Returns:
            List of sentence strings
        """
        import re

        # Improved sentence splitting regex that handles common abbreviations
        sentence_endings = r"[.!?]+(?:\s|$)"
        abbreviations = (
            r"(?:Mr|Mrs|Dr|Prof|Sr|Jr|vs|etc|Inc|Ltd|Corp|Co|St|Ave|Rd|Blvd|"
            r"Apt|No|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Mon|Tue|"
            r"Wed|Thu|Fri|Sat|Sun)\.(?!\s*$)"
        )

        # Split on sentence endings, but not after abbreviations
        sentences = []
        current_sentence = ""

        for char in text:
            current_sentence += char
            if re.search(sentence_endings, current_sentence):
                # Check if this is likely an abbreviation
                if not re.search(abbreviations, current_sentence):
                    sentences.append(current_sentence.strip())
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
        """
        Compute embeddings for a list of sentences asynchronously and non-blocking.

        Args:
            sentences: List of sentence strings

        Returns:
            numpy array of embeddings
        """
        import asyncio
        import concurrent.futures
        import os

        import psutil

        # Ensure model is loaded before use
        await self._initialize_model()

        try:
            # Get CPU count and current load for adaptive batching
            cpu_count = os.cpu_count() or 4
            cpu_load = psutil.cpu_percent(interval=0.1)

            # Adaptive batch sizing optimized for your Intel Ultra 9 185H (22 cores)
            # and RTX 4070 GPU setup
            import torch

            # Check if we have GPU acceleration
            has_gpu = (
                torch.cuda.is_available()
                and hasattr(self, "_embedding_model")
                and self._embedding_model is not None
                and next(self._embedding_model.parameters()).device.type == "cuda"
            )

            if has_gpu:
                # GPU mode: Use larger batches and more CPU workers for preprocessing
                if cpu_load > 80:
                    max_workers = min(4, cpu_count // 4)  # Still use multiple workers
                    batch_size = min(50, len(sentences))  # Larger batches for GPU
                elif cpu_load > 50:
                    max_workers = min(8, cpu_count // 2)  # More workers available
                    batch_size = min(100, len(sentences))  # Bigger batches
                else:
                    # Low CPU load: maximize parallel processing
                    max_workers = min(12, cpu_count)  # Use more of your 22 cores
                    batch_size = min(200, len(sentences))  # Large GPU batches
            else:
                # CPU-only mode: More conservative batching
                if cpu_load > 80:
                    max_workers = min(2, cpu_count // 8)
                    batch_size = min(10, len(sentences))
                elif cpu_load > 50:
                    max_workers = min(4, cpu_count // 4)
                    batch_size = min(25, len(sentences))
                else:
                    max_workers = min(6, cpu_count // 2)  # Still use good parallelism
                    batch_size = min(50, len(sentences))

            logger.info(
                f"Processing {len(sentences)} sentences with {max_workers} workers, batch_size={batch_size}, CPU load={cpu_load}%"
            )

            # Process in batches to avoid blocking
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
                    logger.debug(f"Embedding progress: {progress}%")

            # Combine all batch results
            if len(all_embeddings) == 1:
                return np.array(all_embeddings[0])
            else:
                return np.vstack(all_embeddings)

        except Exception as e:
            logger.error(f"Error computing sentence embeddings: {e}")
            # Return zero embeddings as fallback
            try:
                dim = self._embedding_model.get_sentence_embedding_dimension()
                return np.zeros((len(sentences), dim))
            except Exception:
                # Fallback dimension if model access fails
                return np.zeros((len(sentences), 384))

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
                    "Using sync embedding method in async context. Use _compute_sentence_embeddings_async instead."
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

    def _create_chunks_with_boundaries(
        self, sentences: List[str], boundaries: List[int], distances: List[float]
    ) -> List[SemanticChunk]:
        """
        Create semantic chunks based on identified boundaries.

        Args:
            sentences: List of sentences
            boundaries: List of boundary indices
            distances: Semantic distances for scoring

        Returns:
            List of SemanticChunk objects
        """
        chunks = []
        start_idx = 0

        # Add final boundary to ensure we capture the last chunk
        final_boundaries = boundaries + [len(sentences)]

        for boundary in final_boundaries:
            if boundary <= start_idx:
                continue

            # Extract sentences for this chunk
            chunk_sentences = sentences[start_idx:boundary]
            chunk_content = " ".join(chunk_sentences)

            # Check size constraints
            if len(chunk_content) < self.min_chunk_size and chunks:
                # Merge with previous chunk if too small
                prev_chunk = chunks[-1]
                merged_sentences = prev_chunk.sentences + chunk_sentences
                merged_content = " ".join(merged_sentences)

                # Update previous chunk
                chunks[-1] = SemanticChunk(
                    content=merged_content,
                    start_index=prev_chunk.start_index,
                    end_index=boundary,
                    sentences=merged_sentences,
                    semantic_score=0.8,  # Default high coherence for merged chunks
                    metadata={"merged": True, "original_boundary": boundary},
                )
            elif len(chunk_content) > self.max_chunk_size:
                # Split large chunks further
                sub_chunks = self._split_large_chunk(chunk_sentences, start_idx)
                chunks.extend(sub_chunks)
            else:
                # Create regular chunk
                chunk = SemanticChunk(
                    content=chunk_content,
                    start_index=start_idx,
                    end_index=boundary,
                    sentences=chunk_sentences,
                    semantic_score=0.8,  # Default high coherence - async calculation expensive
                    metadata={"boundary_type": "semantic"},
                )
                chunks.append(chunk)

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
            logger.error(f"Error calculating chunk coherence: {e}")
            return 0.5  # Default neutral score

    async def chunk_text(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[SemanticChunk]:
        """
        Chunk text using semantic analysis.

        Args:
            text: Input text to chunk
            metadata: Optional metadata to attach to chunks

        Returns:
            List of SemanticChunk objects
        """
        try:
            logger.info(f"Starting semantic chunking of text ({len(text)} characters)")

            # Step 1: Split into sentences
            sentences = self._split_into_sentences(text)
            if len(sentences) <= 1:
                # Single sentence or empty text
                chunk = SemanticChunk(
                    content=text,
                    start_index=0,
                    end_index=1,
                    sentences=sentences,
                    semantic_score=1.0,
                    metadata=metadata or {"single_sentence": True},
                )
                return [chunk]

            logger.debug(f"Split text into {len(sentences)} sentences")

            # Step 2: Compute sentence embeddings asynchronously
            embeddings = await self._compute_sentence_embeddings_async(sentences)

            # Step 3: Calculate semantic distances
            distances = self._compute_semantic_distances(embeddings)

            # Step 4: Find chunk boundaries
            boundaries = self._find_chunk_boundaries(distances)

            logger.debug(f"Found {len(boundaries)} semantic boundaries")

            # Step 5: Create chunks
            chunks = self._create_chunks_with_boundaries(
                sentences, boundaries, distances
            )

            # Add metadata to chunks
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

            avg_coherence = np.mean([c.semantic_score for c in chunks])
            logger.info(
                f"Created {len(chunks)} semantic chunks with average "
                f"coherence: {avg_coherence:.3f}"
            )

            return chunks

        except Exception as e:
            logger.error(f"Error in semantic chunking: {e}")
            # Fallback to simple sentence-based chunking
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


# Global instance placeholder - will be created lazily
_semantic_chunker_instance = None


def get_semantic_chunker():
    """Get the global semantic chunker instance (lazy initialization)."""
    global _semantic_chunker_instance
    if _semantic_chunker_instance is None:
        _semantic_chunker_instance = AutoBotSemanticChunker()
    return _semantic_chunker_instance
