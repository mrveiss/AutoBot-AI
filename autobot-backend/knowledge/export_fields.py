# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Field selection for knowledge-base exports (moved out of ``knowledge/bulk.py``, #19163).

A research-quarantined fact keeps its ``collection`` marker whatever fields the export drops, so a
restore or re-import puts it back quarantined, never as a trusted fact.
"""

from __future__ import annotations

from typing import Any, Dict, List


def filter_fact_fields(
    facts: List[Dict[str, Any]],
    include_metadata: bool,
    include_tags: bool,
) -> List[Dict[str, Any]]:
    """
    Filter fact fields based on include flags.

    Issue #415: Control what fields are included in export.
    """
    result = []
    for fact in facts:
        filtered_fact = {
            "fact_id": fact.get("fact_id"),
            "content": fact.get("content"),
        }

        # Include timestamp if present
        if "timestamp" in fact:
            filtered_fact["timestamp"] = fact["timestamp"]

        # Include embedding if present
        if "embedding" in fact:
            filtered_fact["embedding"] = fact["embedding"]
            filtered_fact["embedding_model"] = fact.get("embedding_model")

        if include_metadata:
            metadata = fact.get("metadata", {}).copy()
            if not include_tags:
                metadata.pop("tags", None)
            filtered_fact["metadata"] = metadata
        elif include_tags:
            # Only tags requested, not full metadata
            tags = fact.get("metadata", {}).get("tags", [])
            filtered_fact["tags"] = tags

        marker = (fact.get("metadata") or {}).get("collection")
        if marker:  # #19163: the quarantine marker survives every field selection
            filtered_fact.setdefault("metadata", {})["collection"] = marker

        result.append(filtered_fact)

    return result
