# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Rule-based tool output extractors for belief state (MVA-1407).

Each extractor implements `extract(tool_output) -> list[(key, value, confidence)]`.
The EXTRACTOR_REGISTRY maps tool names to extractor instances.
"""

from __future__ import annotations

from agent_loop.extractors.read_file import ReadFileExtractor
from agent_loop.extractors.run_command import RunCommandExtractor
from agent_loop.extractors.web_search import WebSearchExtractor

EXTRACTOR_REGISTRY: dict[str, object] = {
    "read_file": ReadFileExtractor(),
    "run_command": RunCommandExtractor(),
    "web_search": WebSearchExtractor(),
}

__all__ = [
    "EXTRACTOR_REGISTRY",
    "ReadFileExtractor",
    "RunCommandExtractor",
    "WebSearchExtractor",
]
