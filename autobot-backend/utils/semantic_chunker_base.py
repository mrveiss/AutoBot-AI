# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared base class for AutoBot semantic chunkers.

Issue #5363: Consolidates the ~60-70% overlap between
`semantic_chunker.py` (CPU) and `semantic_chunker_gpu.py` (GPU).
Only the hardware-specific `_initialize_model` and `_compute_embeddings`
steps are abstract; everything else (sentence splitting, semantic
distance, boundary detection, chunk assembly with min/max-size
constraints, fallback chunking, document-format conversion) lives here.
"""

import os

from autobot_shared.ssot_config import config

# CRITICAL FIX: Force tf-keras usage before importing transformers/sentence-transformers.
# The subclasses import torch/sentence_transformers lazily, but having these set at module
# load time keeps behavior identical to the pre-refactor `semantic_chunker*.py` files.
config.tf_use_legacy_keras = "1"
config.keras_backend = "tensorflow"

# Reduce Hugging Face rate limiting and improve caching
config.hf_hub_disable_progress_bars = "1"
config.transformers_offline = "0"  # Allow downloads but cache aggressively
config.hf_hub_cache = os.path.expanduser("~/.cache/huggingface")
config.huggingface_hub_cache = os.path.expanduser("~/.cache/huggingface")

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np

from autobot_shared.logging_manager import get_llm_logger

logger = get_llm_logger("semantic_chunker_base")

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


class SemanticChunkerBase(ABC):
    """
    Shared pipeline for CPU and GPU semantic chunkers.

    Subclasses implement `_initialize_model()` and `_compute_embeddings()`.
    Everything else (sentence splitting, cosine distances, percentile
    boundaries, size-constrained chunk assembly, fallback) is inherited.
    """

    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        percentile_threshold: float = 95.0,
        min_chunk_size: int = 100,
        max_chunk_size: int = 1000,
        overlap_sentences: int = 1,
    ):
        self.embedding_model_name = embedding_model
        self.percentile_threshold = percentile_threshold
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_sentences = overlap_sentences
        self._embedding_model = None

    # ------------------------------------------------------------------
    # Hardware-specific hooks (abstract)
    # ------------------------------------------------------------------

    @abstractmethod
    async def _initialize_model(self) -> None:
        """Load the embedding model. Implementation is hardware-specific."""

    @abstractmethod
    async def _compute_embeddings(self, sentences: List[str]) -> np.ndarray:
        """Compute sentence embeddings. Implementation is hardware-specific."""

    # ------------------------------------------------------------------
    # Shared pipeline
    # ------------------------------------------------------------------

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences with abbreviation awareness (Issue #380/#383)."""
        raw_splits = _SENTENCE_ENDINGS_RE.split(text)

        sentences: List[str] = []
        current_sentence = ""
        for part in raw_splits:
            current_sentence += part
            if _SENTENCE_ENDING_MATCH_RE.match(part):
                if not _ABBREVIATIONS_RE.search(current_sentence):
                    stripped = current_sentence.strip()
                    if stripped:
                        sentences.append(stripped)
                    current_sentence = ""

        if current_sentence.strip():
            sentences.append(current_sentence.strip())

        # Filter out very short sentences (likely parsing errors)
        return [s for s in sentences if len(s.split()) >= 3]

    def _compute_semantic_distances(self, embeddings: np.ndarray) -> List[float]:
        """Cosine distance between consecutive sentence embeddings."""
        if len(embeddings) <= 1:
            return []

        from sklearn.metrics.pairwise import cosine_similarity

        distances: List[float] = []
        for i in range(len(embeddings) - 1):
            similarity = cosine_similarity(embeddings[i].reshape(1, -1), embeddings[i + 1].reshape(1, -1))[0][0]
            distances.append(1 - similarity)

        return distances

    def _find_chunk_boundaries(self, distances: List[float]) -> List[int]:
        """Percentile-based boundary detection."""
        if not distances:
            return []

        threshold = np.percentile(distances, self.percentile_threshold)
        return [i + 1 for i, distance in enumerate(distances) if distance > threshold]

    # ---- Chunk assembly helpers (Issue #620) --------------------------

    def _merge_with_previous_chunk(
        self, chunks: List[SemanticChunk], chunk_sentences: List[str], boundary: int
    ) -> None:
        """Merge a too-small chunk into the previous one."""
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
        return SemanticChunk(
            content=chunk_content,
            start_index=start_idx,
            end_index=boundary,
            sentences=chunk_sentences,
            semantic_score=0.8,
            metadata={"boundary_type": "semantic"},
        )

    def _create_size_constrained_chunk(
        self,
        sentences: List[str],
        sentence_idx: int,
        is_final: bool = False,
    ) -> SemanticChunk:
        chunk_content = " ".join(sentences)
        metadata: Dict[str, Any] = {"split_type": "size_constraint"}
        if is_final:
            metadata["final_chunk"] = True

        return SemanticChunk(
            content=chunk_content,
            start_index=sentence_idx - len(sentences),
            end_index=sentence_idx,
            sentences=sentences if is_final else sentences.copy(),
            semantic_score=0.7,
            metadata=metadata,
        )

    def _apply_overlap_reset(self, current_sentences: List[str]) -> tuple[List[str], int]:
        if self.overlap_sentences > 0:
            overlap_start = -self.overlap_sentences
            new_sentences = current_sentences[overlap_start:]
            return new_sentences, sum(len(s) for s in new_sentences)
        return [], 0

    def _split_large_chunk(self, sentences: List[str], start_idx: int) -> List[SemanticChunk]:
        chunks: List[SemanticChunk] = []
        current_sentences: List[str] = []
        current_length = 0
        sentence_idx = start_idx

        for sentence in sentences:
            sentence_len = len(sentence)

            if current_length + sentence_len > self.max_chunk_size and current_sentences:
                chunks.append(self._create_size_constrained_chunk(current_sentences, sentence_idx))
                current_sentences, current_length = self._apply_overlap_reset(current_sentences)

            current_sentences.append(sentence)
            current_length += sentence_len
            sentence_idx += 1

        if current_sentences:
            chunks.append(self._create_size_constrained_chunk(current_sentences, sentence_idx, is_final=True))

        return chunks

    def _create_chunks_with_boundaries(
        self, sentences: List[str], boundaries: List[int], distances: List[float]
    ) -> List[SemanticChunk]:
        """Chunk assembly with min/max size handling (Issue #620)."""
        chunks: List[SemanticChunk] = []
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
                chunks.append(self._create_regular_chunk(chunk_content, chunk_sentences, start_idx, boundary))

            start_idx = boundary - self.overlap_sentences if self.overlap_sentences > 0 else boundary

        return chunks

    # ---- Single-sentence + metadata helpers ---------------------------

    def _create_single_sentence_chunk(
        self, text: str, sentences: List[str], metadata: Dict[str, Any] | None
    ) -> SemanticChunk:
        return SemanticChunk(
            content=text,
            start_index=0,
            end_index=1,
            sentences=sentences,
            semantic_score=1.0,
            metadata=metadata or {"single_sentence": True},
        )

    def _build_chunk_metadata(
        self, chunk_index: int, total_chunks: int, metadata: Dict[str, Any] | None
    ) -> Dict[str, Any]:
        """Metadata fields shared by all backends. Subclasses add their own via _extra_chunk_metadata()."""
        base = {
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "source_metadata": metadata or {},
            "embedding_model": self.embedding_model_name,
        }
        base.update(self._extra_chunk_metadata())
        return base

    def _extra_chunk_metadata(self) -> Dict[str, Any]:
        """Subclass hook for backend-specific chunk metadata."""
        return {"chunking_method": "semantic", "percentile_threshold": self.percentile_threshold}

    def _enrich_chunks_with_metadata(self, chunks: List[SemanticChunk], metadata: Dict[str, Any] | None) -> None:
        for i, chunk in enumerate(chunks):
            chunk.metadata.update(self._build_chunk_metadata(i, len(chunks), metadata))

    # ---- Fallback chunking --------------------------------------------

    def _create_fallback_chunk(
        self,
        sentences: List[str],
        start_index: int,
        end_index: int,
        metadata: Dict[str, Any] | None = None,
    ) -> SemanticChunk:
        chunk_content = " ".join(sentences)
        return SemanticChunk(
            content=chunk_content,
            start_index=start_index,
            end_index=end_index,
            sentences=sentences.copy() if sentences else [],
            semantic_score=0.5,
            metadata={"fallback_chunking": True, **(metadata or {})},
        )

    async def _fallback_chunking(self, text: str, metadata: Dict[str, Any] | None = None) -> List[SemanticChunk]:
        logger.warning("Using fallback chunking method")

        sentences = self._split_into_sentences(text)
        chunks: List[SemanticChunk] = []
        current_sentences: List[str] = []
        current_length = 0

        for i, sentence in enumerate(sentences):
            sentence_len = len(sentence)

            if current_length + sentence_len > self.max_chunk_size and current_sentences:
                chunks.append(self._create_fallback_chunk(current_sentences, i - len(current_sentences), i, metadata))
                current_sentences = []
                current_length = 0

            current_sentences.append(sentence)
            current_length += sentence_len

        if current_sentences:
            chunks.append(
                self._create_fallback_chunk(
                    current_sentences,
                    len(sentences) - len(current_sentences),
                    len(sentences),
                    metadata,
                )
            )

        return chunks

    # ---- Public entry points ------------------------------------------

    async def chunk_text(self, text: str, metadata: Dict[str, Any] | None = None) -> List[SemanticChunk]:
        """Chunk text using semantic analysis (Issue #620)."""
        try:
            logger.info("Starting semantic chunking of text (%d characters)", len(text))

            sentences = self._split_into_sentences(text)
            if len(sentences) <= 1:
                return [self._create_single_sentence_chunk(text, sentences, metadata)]

            logger.debug("Split text into %d sentences", len(sentences))

            await self._initialize_model()
            embeddings = await self._compute_embeddings(sentences)
            distances = self._compute_semantic_distances(embeddings)
            boundaries = self._find_chunk_boundaries(distances)

            logger.debug("Found %d semantic boundaries", len(boundaries))

            chunks = self._create_chunks_with_boundaries(sentences, boundaries, distances)
            self._enrich_chunks_with_metadata(chunks, metadata)

            if chunks:
                avg_coherence = float(np.mean([c.semantic_score for c in chunks]))
                logger.info(
                    "Created %d semantic chunks with average coherence: %.3f",
                    len(chunks),
                    avg_coherence,
                )

            return chunks

        except Exception as e:
            logger.error("Error in semantic chunking: %s", e)
            return await self._fallback_chunking(text, metadata)

    async def chunk_document(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """LlamaIndex-compatible document interface."""
        semantic_chunks = await self.chunk_text(content, metadata)

        return [
            {
                "text": chunk.content,
                "metadata": {
                    **chunk.metadata,
                    "semantic_score": chunk.semantic_score,
                    "sentence_count": len(chunk.sentences),
                    "character_count": len(chunk.content),
                },
            }
            for chunk in semantic_chunks
        ]
