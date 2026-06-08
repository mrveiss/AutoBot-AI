# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Extractor for web_search tool output (MVA-1407).

Keys produced:
  web_search:{slugified_query}:answered   → bool, confidence 0.8
  web_search:{slugified_query}:top_entity → str, confidence 0.7
"""

from __future__ import annotations

import re
from typing import Any


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:80]


def _has_answer(tool_output: dict) -> bool:
    """Heuristic: result has content and no error."""
    if tool_output.get("error"):
        return False
    results = tool_output.get("results") or tool_output.get("items") or []
    if results:
        return True
    content = tool_output.get("content") or tool_output.get("answer") or tool_output.get("text")
    return bool(content)


def _top_entity(tool_output: dict) -> str | None:
    """Extract the title of the first result as the top entity."""
    results = tool_output.get("results") or tool_output.get("items") or []
    if results and isinstance(results, list):
        first = results[0]
        if isinstance(first, dict):
            return first.get("title") or first.get("name") or first.get("url")
        if isinstance(first, str):
            return first
    return tool_output.get("top_result") or tool_output.get("entity")


class WebSearchExtractor:
    """Extract topic-answered and top-entity assertions from web_search output."""

    def extract(self, tool_output: Any) -> list[tuple[str, Any, float]]:
        if not isinstance(tool_output, dict):
            return []

        query = tool_output.get("query") or tool_output.get("q") or tool_output.get("search_query") or ""
        if not query:
            return []

        slug = _slugify(str(query))
        results: list[tuple[str, Any, float]] = []

        answered = _has_answer(tool_output)
        results.append((f"web_search:{slug}:answered", answered, 0.8))

        entity = _top_entity(tool_output)
        if entity:
            results.append((f"web_search:{slug}:top_entity", str(entity), 0.7))

        return results
