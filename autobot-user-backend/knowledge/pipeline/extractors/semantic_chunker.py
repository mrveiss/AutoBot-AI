# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Semantic Chunker - Chunks text by semantic boundaries.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import logging
import re
from typing import Any, AsyncIterator, List

from ..base import BaseExtractor, PipelineContext
from ..models import ProcessedChunk
from ..registry import TaskRegistry

logger = logging.getLogger(__name__)


@TaskRegistry.register_extractor("chunk_text")
class SemanticChunker(BaseExtractor):
    """
    Semantic text chunker with paragraph/heading awareness.

    Chunks by semantic boundaries (paragraphs, headings) rather than
    fixed token counts. Respects configurable max_tokens and overlap.
    """

    def __init__(self, **kwargs):
        """
        Initialize semantic chunker.

        Args:
            max_tokens: Maximum tokens per chunk (default: 512)
            overlap: Overlap tokens between chunks (default: 50)
        """
        self.max_tokens = kwargs.get("max_tokens", 512)
        self.overlap = kwargs.get("overlap", 50)

    async def process(
        self, input_data: Any, context: PipelineContext
    ) -> AsyncIterator[ProcessedChunk]:
        """
        Chunk text and yield ProcessedChunk objects.

        Args:
            input_data: Document text (str)
            context: Pipeline context

        Yields:
            ProcessedChunk objects
        """
        if not isinstance(input_data, str):
            logger.warning("Input is not string, skipping chunking")
            return

        document_type = context.metadata.get("document_type", "unknown")
        chunks = self._chunk_text(input_data)

        for idx, chunk_text in enumerate(chunks):
            start_offset, end_offset = self._calculate_offsets(
                input_data, chunk_text, idx
            )

            yield ProcessedChunk(
                content=chunk_text,
                document_id=context.document_id,
                chunk_index=idx,
                metadata={"chunk_method": "semantic"},
                document_type=document_type,
                start_offset=start_offset,
                end_offset=end_offset,
            )

    def _chunk_text(self, text: str) -> List[str]:
        """
        Chunk text by semantic boundaries. Helper for process (Issue #665).

        Args:
            text: Document text

        Returns:
            List of chunk strings
        """
        segments = self._split_into_segments(text)
        chunks = []
        current_chunk = []
        current_tokens = 0

        for segment in segments:
            segment_tokens = self._estimate_tokens(segment)

            if current_tokens + segment_tokens > self.max_tokens and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = current_chunk[-self.overlap :] if self.overlap else []
                current_tokens = sum(self._estimate_tokens(s) for s in current_chunk)

            current_chunk.append(segment)
            current_tokens += segment_tokens

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def _split_into_segments(self, text: str) -> List[str]:
        """
        Split text into semantic segments. Helper for _chunk_text (Issue #665).

        Args:
            text: Document text

        Returns:
            List of segment strings (paragraphs, sentences)
        """
        segments = re.split(r"\n\s*\n", text)
        segments = [s.strip() for s in segments if s.strip()]

        result = []
        for segment in segments:
            if len(segment) > self.max_tokens * 4:
                sentences = re.split(r"(?<=[.!?])\s+", segment)
                result.extend(sentences)
            else:
                result.append(segment)

        return result

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count. Helper for _chunk_text (Issue #665).

        Args:
            text: Text string

        Returns:
            Estimated token count
        """
        return len(text.split())

    def _calculate_offsets(
        self, full_text: str, chunk_text: str, chunk_index: int
    ) -> tuple[int, int]:
        """
        Calculate chunk offsets. Helper for process (Issue #665).

        Args:
            full_text: Full document text
            chunk_text: Chunk text
            chunk_index: Chunk index

        Returns:
            Tuple of (start_offset, end_offset)
        """
        try:
            start_offset = full_text.find(chunk_text)
            if start_offset == -1:
                start_offset = chunk_index * self.max_tokens * 4
            end_offset = start_offset + len(chunk_text)
        except Exception as e:
            logger.warning("Offset calculation error: %s", e)
            start_offset = chunk_index * self.max_tokens * 4
            end_offset = start_offset + len(chunk_text)

        return start_offset, end_offset
