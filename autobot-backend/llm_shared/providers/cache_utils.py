# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM payload cache-determinism helpers (#7368).

Anthropic and OpenAI cache prompts by byte-exact content.  Any
non-deterministic ordering in a request payload (tool list, system
blocks, metadata dicts, plugin contributions) silently invalidates the
5-minute cache TTL even when the user input is identical.

``_sorted_for_cache`` normalises a payload dict *in-place* before it is
handed to the SDK, ensuring two payloads built from the same logical
inputs always serialise identically.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _stable_key(obj: Any) -> str:
    """Return a stable string key for sorting an arbitrary object."""
    if isinstance(obj, dict):
        return obj.get("name") or obj.get("id") or _content_hash(obj)
    return str(obj)


def _content_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:8]


def _sort_payload_value(value: Any) -> Any:
    """Recursively normalise *value* for deterministic serialisation."""
    if isinstance(value, set):
        raise TypeError(
            "set() must not appear in LLM payload — convert to sorted list before "
            "_sorted_for_cache().  Offending value: %r" % value
        )
    if isinstance(value, list):
        # Sort lists of dicts that have a 'name' or 'id' key (tool/function/block lists).
        if value and isinstance(value[0], dict) and ("name" in value[0] or "id" in value[0]):
            value = sorted((_sort_payload_value(item) for item in value), key=_stable_key)
        else:
            value = [_sort_payload_value(item) for item in value]
    elif isinstance(value, dict):
        value = {k: _sort_payload_value(v) for k, v in sorted(value.items())}
    return value


def sorted_for_cache(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *payload* with all cache-sensitive fields normalised.

    Rules applied:
    - ``tools`` / ``functions`` lists are sorted by ``name``.
    - Any list of dicts with a ``name`` or ``id`` field is sorted by that key.
    - Nested ``dict`` values have their keys sorted.
    - Raises ``TypeError`` if any ``set()`` survives to this point.

    *payload* is not mutated; a new dict is returned.
    """
    return {k: _sort_payload_value(v) for k, v in sorted(payload.items())}
