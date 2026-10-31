#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One rule for collapsing dynamic path segments in an endpoint key (#18093).

Two `_normalize_endpoint` implementations existed -- same name, same purpose, different
code -- and the second one did not work:

    autobot-backend/api/analytics_controller.py:122   per-segment, first match wins
    autobot_shared/monitoring/metrics/frontend.py:312 sequential whole-string re.sub

The monitoring copy ran `re.sub(r"/\\d+", "/{id}")` BEFORE its uuid pattern, so the
numeric substitution ate a uuid's leading digits and the uuid pattern could then never
match. Measured:

    /api/x/123e4567-e89b-12d3-a456-426614174000 -> /api/x/{id}e4567-e89b-12d3-a456-426614174000
    /api/commits/4b9a5487f8a1c2d3e4f5           -> /api/commits/{id}b9a5487f8a1c2d3e4f5

A uuid in a path was therefore never collapsed, and SHA-like hex had no pattern at all.
Both leave unbounded values on the `endpoint` label -- the exact cardinality blowup the
function's own docstring said it existed to prevent.

Per-segment with first-match-wins is why the surviving implementation is correct: each
segment is classified once, so no substitution can corrupt the input for the next
pattern.
"""

from __future__ import annotations

import re

__all__ = ["DYNAMIC_SEGMENT_PATTERNS", "collapse_dynamic_segments"]

#: Matched left-to-right; the first hit classifies the segment.
DYNAMIC_SEGMENT_PATTERNS = (
    # UUID: 8-4-4-4-12 hex groups.
    re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I),
    # Long hex strings (SHA-like, >= 16 chars). Absent from the monitoring copy, which
    # is why a commit SHA in a path produced one label value per commit.
    re.compile(r"[0-9a-f]{16,}", re.I),
    # Pure numeric ids.
    re.compile(r"^\d+$"),
    # Generated-looking alphanumeric slugs: contains both a letter and a digit, >= 8
    # chars. The length and the two lookaheads keep short word slugs ("settings",
    # "v2") out of the placeholder.
    re.compile(r"^(?=[a-z0-9_-]{0,200}[a-z])(?=[a-z0-9_-]{0,200}\d)[a-z0-9_-]{8,}$", re.I),
)


def collapse_dynamic_segments(path: str, placeholder: str = "{id}") -> str:
    """Replace each dynamic segment of ``path`` with ``placeholder``.

    A segment is matched against its query-stripped form, but a segment that is NOT
    replaced is preserved verbatim, query string included. That asymmetry is deliberate
    and preserves `analytics_controller`'s existing behaviour exactly -- stripping the
    query globally would change the keys that caller already records.

    Args:
        path: A URL path, with or without a trailing query string.
        placeholder: What a dynamic segment becomes.

    Returns:
        The path with dynamic segments collapsed.

    Examples:
        >>> collapse_dynamic_segments("/api/users/42")
        '/api/users/{id}'
        >>> collapse_dynamic_segments("/api/x/123e4567-e89b-12d3-a456-426614174000")
        '/api/x/{id}'
        >>> collapse_dynamic_segments("/api/commits/4b9a5487f8a1c2d3e4f5a6b7c8d9e0f1a2")
        '/api/commits/{id}'
        >>> collapse_dynamic_segments("/api/settings")
        '/api/settings'
    """
    normalized: list[str] = []
    for segment in path.split("/"):
        if not segment:
            normalized.append(segment)
            continue
        clean = segment.split("?")[0]
        if any(pattern.search(clean) for pattern in DYNAMIC_SEGMENT_PATTERNS):
            normalized.append(placeholder)
        else:
            normalized.append(segment)
    return "/".join(normalized)
