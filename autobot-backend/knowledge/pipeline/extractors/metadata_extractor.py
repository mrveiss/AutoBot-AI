# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Metadata Extractor - Extracts document metadata using heuristics.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import logging
import re
from typing import Any, AsyncIterator, Dict, List

from ..base import BaseExtractor, PipelineContext
from ..registry import TaskRegistry

logger = logging.getLogger(__name__)


@TaskRegistry.register_extractor("extract_metadata")
class MetadataExtractor(BaseExtractor):
    """
    Extracts document metadata using pattern-based heuristics.

    Extracts: title, word_count, language, heading structure,
    URLs, emails without requiring LLM inference.
    """

    def __init__(self, **kwargs):
        """Initialize metadata extractor."""

    async def process(
        self, input_data: Any, context: PipelineContext
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Extract metadata and yield metadata dict.

        Args:
            input_data: Document text (str)
            context: Pipeline context

        Yields:
            Metadata dictionary
        """
        if not isinstance(input_data, str):
            logger.warning("Input is not string, skipping metadata extraction")
            yield {}
            return

        metadata = {
            "title": self._extract_title(input_data),
            "word_count": self._count_words(input_data),
            "language": self._detect_language(input_data),
            "headings": self._extract_headings(input_data),
            "urls": self._extract_urls(input_data),
            "emails": self._extract_emails(input_data),
        }

        logger.info("Extracted metadata: %d fields", len(metadata))
        yield metadata

    def _extract_title(self, text: str) -> str:
        """
        Extract document title. Helper for process (Issue #665).

        Args:
            text: Document text

        Returns:
            Title string or "Untitled"
        """
        lines = text.split("\n")
        for line in lines[:10]:
            line = line.strip()
            if line and len(line) < 100:
                if re.match(r"^#\s+", line):
                    return line.lstrip("#").strip()
                elif line.isupper() or line.istitle():
                    return line

        return "Untitled"

    def _count_words(self, text: str) -> int:
        """Count words. Helper for process (Issue #665)."""
        return len(text.split())

    def _detect_language(self, text: str) -> str:
        """
        Detect document language. Helper for process (Issue #665).

        Args:
            text: Document text

        Returns:
            Language code ("en", "unknown")
        """
        english_words = ["the", "and", "for", "are", "but", "not", "you", "all"]
        sample = text[:1000].lower()
        english_count = sum(1 for word in english_words if word in sample)

        if english_count >= 3:
            return "en"
        return "unknown"

    def _extract_headings(self, text: str) -> List[str]:
        """
        Extract document headings. Helper for process (Issue #665).

        Args:
            text: Document text

        Returns:
            List of heading strings
        """
        headings = []
        lines = text.split("\n")

        for line in lines:
            line = line.strip()
            if re.match(r"^#{1,6}\s+", line):
                heading = re.sub(r"^#{1,6}\s+", "", line)
                headings.append(heading)
            elif line and len(line) < 80 and line[0].isupper():
                if not line.endswith("."):
                    headings.append(line)

        return headings[:20]

    def _extract_urls(self, text: str) -> List[str]:
        """
        Extract URLs. Helper for process (Issue #665).

        Args:
            text: Document text

        Returns:
            List of URL strings
        """
        url_pattern = r"https?://[^\s)]+"
        urls = re.findall(url_pattern, text)
        return list(set(urls))[:50]

    def _extract_emails(self, text: str) -> List[str]:
        """
        Extract email addresses. Helper for process (Issue #665).

        Args:
            text: Document text

        Returns:
            List of email strings
        """
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        emails = re.findall(email_pattern, text)
        return list(set(emails))[:20]
