# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Decoding of a fact's Redis hash (moved out of ``knowledge/facts.py``, #19163).

``knowledge.facts`` re-imports both names, so ``knowledge.facts._decode_redis_hash`` is unchanged for
every caller and test that patches it there.
"""

from __future__ import annotations

import json
from typing import Any, Dict


def _apply_usage_fields(decoded: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    """Surface authoritative usage counters from the Redis hash into metadata.

    A1 (#12552): ``access_count`` / ``last_accessed`` live as top-level hash
    fields (so ``HINCRBY`` stays atomic and the metadata JSON blob is never
    rewritten on access). They are the single source of truth; on read we copy
    them into the returned metadata dict, defaulting to 0 / "" when absent so
    every fact — old or new — exposes the keys.
    """
    try:
        metadata["access_count"] = int(decoded.get("access_count") or 0)
    except (TypeError, ValueError):
        metadata["access_count"] = 0
    metadata["last_accessed"] = decoded.get("last_accessed") or ""


def _decode_redis_hash(fact_data: Dict[bytes, bytes]) -> Dict[str, Any]:
    """Decode Redis hash bytes to strings and parse metadata (Issue #315: extracted).

    Args:
        fact_data: Raw Redis hash data with bytes keys/values

    Returns:
        Decoded dict with parsed metadata
    """
    decoded = {}
    for key, value in fact_data.items():
        k = key.decode("utf-8") if isinstance(key, bytes) else key
        v = value.decode("utf-8") if isinstance(value, bytes) else value
        decoded[k] = v

    # Parse metadata JSON if present
    if "metadata" in decoded:
        try:
            raw = decoded["metadata"]
            decoded["_parsed_metadata"] = raw if isinstance(raw, dict) else json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            decoded["_parsed_metadata"] = {}
    else:
        decoded["_parsed_metadata"] = {}

    return decoded
