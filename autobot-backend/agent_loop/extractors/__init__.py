# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""
Rule-based tool output extractors for belief state (MVA-1407).

Each extractor implements `extract(tool_output) -> list[(key, value, confidence)]`.
The EXTRACTOR_REGISTRY maps tool names to extractor instances.
"""

from __future__ import annotations

from typing import Any

from agent_loop.extractors.config_file import ConfigFileExtractor
from agent_loop.extractors.read_file import ReadFileExtractor
from agent_loop.extractors.run_command import RunCommandExtractor
from agent_loop.extractors.web_search import WebSearchExtractor


class _ChainedExtractor:
    """Run multiple extractors in sequence and merge their results."""

    def __init__(self, *extractors: object) -> None:
        self._extractors = extractors

    def extract(self, tool_output: Any) -> list[tuple[str, Any, float]]:
        results: list[tuple[str, Any, float]] = []
        for extractor in self._extractors:
            results.extend(extractor.extract(tool_output))  # type: ignore[attr-defined]
        return results


EXTRACTOR_REGISTRY: dict[str, object] = {
    "read_file": _ChainedExtractor(ReadFileExtractor(), ConfigFileExtractor()),
    "run_command": RunCommandExtractor(),
    "web_search": WebSearchExtractor(),
}

__all__ = [
    "EXTRACTOR_REGISTRY",
    "ConfigFileExtractor",
    "ReadFileExtractor",
    "RunCommandExtractor",
    "WebSearchExtractor",
]
