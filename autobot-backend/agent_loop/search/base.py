# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Base contract for pluggable web-search providers.

A ``WebSearchProvider`` turns a search request into a normalized list of
``SearchResult`` objects. Concrete providers (SearXNG #9022, Brave #9023)
subclass this and implement ``search`` / ``is_available``.

Mirrors ``llm_shared.base_provider.BaseProvider``: a ``provider_name`` class
attribute, settings-dict constructor, and an async availability probe used by
the registry for credential-gating and fallback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Search result categories mapped onto backend-specific engines/endpoints.
CATEGORY_GENERAL = "general"
CATEGORY_NEWS = "news"
CATEGORY_CODE = "code"
CATEGORY_ACADEMIC = "academic"

DEFAULT_RESULT_COUNT = 10


@dataclass
class SearchResult:
    """One normalized web-search hit shared across all providers."""

    title: str
    url: str
    snippet: str = ""
    freshness: Optional[str] = None
    source: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict (matches the {title,url,snippet} seam shape)."""
        data: Dict[str, Any] = {"title": self.title, "url": self.url, "snippet": self.snippet}
        if self.freshness:
            data["freshness"] = self.freshness
        if self.source:
            data["source"] = self.source
        return data


class WebSearchProvider(ABC):
    """Abstract async web-search backend.

    Subclasses set ``provider_name`` and implement ``search`` + ``is_available``.
    The settings dict carries credentials/instance URLs (never hard-coded).
    """

    provider_name: str = "base"

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        """Store provider settings (credentials, instance URL, options)."""
        self.settings: Dict[str, Any] = settings or {}

    def _get_setting(self, key: str, default: Any = None) -> Any:
        """Safe settings access mirroring ``BaseProvider._get_setting``."""
        return self.settings.get(key, default)

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        category: Optional[str] = None,
        count: int = DEFAULT_RESULT_COUNT,
    ) -> List[SearchResult]:
        """Run a search and return normalized results.

        Implementations must raise on unreachable/error so the registry can
        fall back. Returning ``[]`` means "reachable, no results" (no fallback).
        """
        raise NotImplementedError

    @abstractmethod
    async def is_available(self) -> bool:
        """Return True when this provider is configured and usable."""
        raise NotImplementedError
