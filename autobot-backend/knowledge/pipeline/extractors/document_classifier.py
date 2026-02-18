# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Document Classifier - Classifies documents by type using heuristics.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import logging
import re
from typing import Any, AsyncIterator, Dict

from ..base import BaseExtractor, PipelineContext
from ..registry import TaskRegistry

logger = logging.getLogger(__name__)


@TaskRegistry.register_extractor("classify_document")
class DocumentClassifier(BaseExtractor):
    """
    Classifies documents by type using pattern-based heuristics.

    Detects: technical, narrative, code, data, mixed document types
    without requiring LLM inference (fast, deterministic).
    """

    def __init__(self, **kwargs):
        """Initialize document classifier."""
        self.code_threshold = kwargs.get("code_threshold", 0.2)
        self.data_threshold = kwargs.get("data_threshold", 0.15)

    async def process(
        self, input_data: Any, context: PipelineContext
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Classify document and yield classification metadata.

        Args:
            input_data: Document text (str)
            context: Pipeline context

        Yields:
            Classification metadata dict
        """
        if not isinstance(input_data, str):
            logger.warning("Input is not string, skipping classification")
            yield {"document_type": "unknown"}
            return

        doc_type = self._classify_document(input_data)
        logger.info("Classified document as: %s", doc_type)

        yield {
            "document_type": doc_type,
            "metadata": {"classifier": "heuristic", "length": len(input_data)},
        }

    def _classify_document(self, text: str) -> str:
        """
        Classify document type. Helper for process (Issue #665).

        Args:
            text: Document text

        Returns:
            Document type string
        """
        code_score = self._calculate_code_score(text)
        data_score = self._calculate_data_score(text)

        if code_score > self.code_threshold:
            return "code"
        elif data_score > self.data_threshold:
            return "data"
        elif self._has_technical_markers(text):
            return "technical"
        elif self._has_narrative_markers(text):
            return "narrative"
        else:
            return "mixed"

    def _calculate_code_score(self, text: str) -> float:
        """
        Calculate code likelihood score. Helper for _classify_document (Issue #665).

        Args:
            text: Document text

        Returns:
            Code score (0.0 to 1.0)
        """
        lines = text.split("\n")
        if not lines:
            return 0.0

        code_patterns = [
            r"^\s*(def|class|import|from|function|const|let|var)\s+",
            r"[{};]\s*$",
            r"^\s*(public|private|protected|static)\s+",
            r"^\s*//|^\s*/\*|^\s*#",
        ]

        code_lines = sum(
            1
            for line in lines
            if any(re.search(pattern, line) for pattern in code_patterns)
        )

        return code_lines / len(lines)

    def _calculate_data_score(self, text: str) -> float:
        """
        Calculate data format score. Helper for _classify_document (Issue #665).

        Args:
            text: Document text

        Returns:
            Data score (0.0 to 1.0)
        """
        data_patterns = [
            r"^\s*\{",
            r"^\s*\[",
            r"^\s*\w+\s*[:=]\s*",
            r",\s*$",
        ]

        lines = text.split("\n")
        if not lines:
            return 0.0

        data_lines = sum(
            1
            for line in lines
            if any(re.search(pattern, line) for pattern in data_patterns)
        )

        return data_lines / len(lines)

    def _has_technical_markers(self, text: str) -> bool:
        """Check for technical document markers. Helper (Issue #665)."""
        technical_markers = [
            r"\b(algorithm|implementation|system|architecture|protocol)\b",
            r"\b(API|HTTP|REST|JSON|XML)\b",
            r"```",
            r"^\s*#+\s+",
        ]
        return any(
            re.search(marker, text, re.IGNORECASE) for marker in technical_markers
        )

    def _has_narrative_markers(self, text: str) -> bool:
        """Check for narrative document markers. Helper (Issue #665)."""
        narrative_markers = [
            r"\b(story|chapter|once upon|narrator)\b",
            r'[""].*?[""]',
            r"^\s*Chapter\s+\d+",
        ]
        return any(
            re.search(marker, text, re.IGNORECASE) for marker in narrative_markers
        )
