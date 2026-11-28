# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure text helpers of the context suggestions.

Split out of ``knowledge/suggestions.py`` (#16665) so that grandfathered module does not grow.
"""

from typing import Any, Dict


def build_snippet(content: str, snippet_length: int, ellipsis: str) -> str:
    """Extract a short preview snippet from raw document content.

    Trims to the nearest word boundary and appends *ellipsis* when truncated.

    Args:
        content: Full document text.
        snippet_length: Maximum character length of the snippet.
        ellipsis: Suffix appended to a truncated snippet.

    Returns:
        Snippet string, at most snippet_length characters + ellipsis.
    """
    if not content:
        return ""
    text = content.strip()
    if len(text) <= snippet_length:
        return text
    truncated = text[:snippet_length].rsplit(" ", 1)[0]
    return truncated + ellipsis


def kb_document_title(content: str, metadata: Dict[str, Any]) -> str:
    """Derive a human-readable title for a KB document.

    Priority: metadata["title"] > metadata["source"] > first non-empty line.

    Args:
        content: Document text.
        metadata: Fact metadata dict.

    Returns:
        Title string (never empty -- falls back to truncated content).
    """
    for key in ("title", "source"):
        val = metadata.get(key, "")
        if val and isinstance(val, str) and val.strip():
            return val.strip()

    for line in content.splitlines():
        line = line.strip()
        if line:
            return line[:120]

    return content[:60].strip() or "Untitled"
