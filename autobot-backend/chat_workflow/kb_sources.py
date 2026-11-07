# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge-base citation mapping, moved out of ``manager.py`` (#21023: that file is over its size ceiling)."""

from typing import Any, Dict, List


def _kb_sources_from_citations(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map raw knowledge-base citation dicts to the persisted sources shape.

    Issue #13296: extracted from ``_persist_workflow_messages`` — was
    duplicated inline for the per-``WorkflowMessage`` citation list (already
    tagged ``type='knowledge_base'`` by ``_build_source_list``) and, per
    #13292, for the completed streamed reply's citations (the raw
    ``rag_citations`` list, which never carries the always-appended
    ``llm_training`` placeholder in the first place).
    """
    return [
        {
            "title": c.get("title") or c.get("source", ""),
            "path": c.get("source", ""),
            "score": c.get("score", 0.0),
            "chunk_id": c.get("id", ""),
        }
        for c in citations
    ]
