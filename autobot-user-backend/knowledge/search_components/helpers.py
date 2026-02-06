# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Search Helper Functions

Issue #381: Extracted from search.py god class refactoring.
Contains utility functions for Redis hash operations and result building.
"""

import json
from typing import Any, Dict, Optional, Set


def decode_redis_hash(fact_data: Dict) -> Dict[str, str]:
    """Decode Redis hash bytes to strings (Issue #315)."""
    decoded = {}
    for k, v in fact_data.items():
        dk = k.decode("utf-8") if isinstance(k, bytes) else k
        dv = v.decode("utf-8") if isinstance(v, bytes) else v
        decoded[dk] = dv
    return decoded


def matches_category(decoded: Dict[str, str], category: Optional[str]) -> bool:
    """Check if fact matches category filter (Issue #315)."""
    if not category:
        return True
    try:
        metadata = json.loads(decoded.get("metadata", "{}"))
        return metadata.get("category") == category
    except json.JSONDecodeError:
        return False


def score_fact_by_terms(decoded: Dict[str, str], query_terms: Set[str]) -> float:
    """Calculate term match score for a fact (Issue #315)."""
    content = decoded.get("content", "").lower()
    matches = sum(1 for term in query_terms if term in content)
    return matches / len(query_terms) if matches > 0 else 0


def build_search_result(
    decoded: Dict[str, str], key: bytes, score: float
) -> Dict[str, Any]:
    """Build search result dict from decoded fact (Issue #315)."""
    fact_id = (
        key.decode("utf-8").replace("fact:", "")
        if isinstance(key, bytes)
        else key.replace("fact:", "")
    )
    try:
        metadata = json.loads(decoded.get("metadata", "{}"))
    except json.JSONDecodeError:
        metadata = {}

    return {
        "content": decoded.get("content", ""),
        "score": score,
        "metadata": {**metadata, "fact_id": fact_id},
        "node_id": fact_id,
        "doc_id": fact_id,
    }
