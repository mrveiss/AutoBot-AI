# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Extractor for read_file tool output (MVA-1407).

Keys produced:
  read_file:{path}:exists   → bool, confidence 1.0
  read_file:{path}:hash     → str (sha256 first 8 hex chars), confidence 1.0
"""

from __future__ import annotations

import hashlib
from typing import Any


class ReadFileExtractor:
    """Extract file-existence and content-hash assertions from read_file output."""

    def extract(self, tool_output: Any) -> list[tuple[str, Any, float]]:
        """Return list of (key, value, confidence) triples."""
        if not isinstance(tool_output, dict):
            return []

        path = tool_output.get("path") or tool_output.get("file_path") or tool_output.get("filename")
        if not path:
            return []

        results: list[tuple[str, Any, float]] = []

        error = tool_output.get("error")
        if error:
            # File missing or unreadable
            results.append((f"read_file:{path}:exists", False, 1.0))
            return results

        content = tool_output.get("content") or tool_output.get("text") or tool_output.get("data")
        if content is None:
            return []

        results.append((f"read_file:{path}:exists", True, 1.0))

        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        elif isinstance(content, bytes):
            content_bytes = content
        else:
            content_bytes = str(content).encode("utf-8")

        content_hash = hashlib.sha256(content_bytes).hexdigest()[:8]
        results.append((f"read_file:{path}:hash", content_hash, 1.0))

        return results
