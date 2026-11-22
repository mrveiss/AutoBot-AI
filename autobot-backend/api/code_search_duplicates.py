# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response builders for the code-search duplicate analytics, and the scope both analytics report."""

#: The index keys files by their path relative to the indexed root and does not record the root, so
#: a search cannot be limited to one root. `analysis_root` is what was indexed, not a filter (#20224).
RESULTS_SCOPE = "whole_index"


def build_duplicates_response(patterns_count: int, duplicate_candidates: list, root_path: str) -> dict:
    """
    Build the response dictionary for duplicate detection.

    Issue #665: Extracted from find_code_duplicates.
    """
    return {
        "summary": {
            "analysis_root": root_path,
            "results_scope": RESULTS_SCOPE,
            "patterns_analyzed": patterns_count,
            "duplicate_candidates_found": len(duplicate_candidates),
            "total_similar_blocks": sum(len(c["similar_blocks"]) for c in duplicate_candidates),
            "highest_priority_pattern": (duplicate_candidates[0]["pattern"] if duplicate_candidates else None),
        },
        "duplicate_candidates": duplicate_candidates[:10],
        "recommendations": [
            "Consider extracting common patterns into utility functions",
            "Look for opportunities to create base classes or mixins",
            "Evaluate if similar error handling can be centralized",
            "Check if configuration loading can be standardized",
            "Consider creating shared validation utilities",
        ],
    }


def build_duplicate_candidate(pattern: str, similar_blocks: list) -> dict:
    """
    Build a duplicate candidate entry from similar blocks.

    Issue #281: Extracted from find_code_duplicates to reduce function length
    and centralize candidate building logic.

    Args:
        pattern: The pattern name that matched
        similar_blocks: List of similar block entries

    Returns:
        Dict with duplicate candidate info including refactor priority
    """
    return {
        "pattern": pattern,
        "similar_blocks": similar_blocks,
        "potential_savings": (f"Could refactor {len(similar_blocks)} similar blocks"),
        "refactor_priority": (len(similar_blocks) * max(block["confidence"] for block in similar_blocks)),
    }
