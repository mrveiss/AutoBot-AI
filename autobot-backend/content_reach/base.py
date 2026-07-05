# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Core abstractions for Content Reach backends (#10932)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from source_attribution import SourceReliability, SourceType


class BackendError(Exception):
    """Raised by a ContentBackend when a fetch attempt fails."""


@dataclass
class ContentRequest:
    """A request for external content."""

    query: str = ""
    url: str = ""
    source: str = ""
    limit: int = 5
    conversation_id: str = "content-reach"
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentResult:
    """Normalized result returned by a backend."""

    success: bool
    source_type: SourceType
    backend_used: str
    text: str = ""
    structured: dict[str, Any] = field(default_factory=dict)
    url: str = ""
    reliability: SourceReliability = SourceReliability.MEDIUM
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def failure(cls, source_type: SourceType, detail: str) -> "ContentResult":
        """Build a non-successful result carrying an error detail."""
        return cls(
            success=False,
            source_type=source_type,
            backend_used="none",
            metadata={"error": detail},
        )


class ContentBackend(ABC):
    """A single way to fetch content for a source (e.g. ddgs, jina, browser)."""

    name: str
    source_type: SourceType

    @abstractmethod
    async def probe(self) -> bool:
        """Return True if this backend is actually working right now."""

    @abstractmethod
    async def fetch(self, request: ContentRequest) -> ContentResult:
        """Fetch content; raise BackendError (or return success=False) on failure."""
