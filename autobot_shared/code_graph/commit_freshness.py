# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Is the commit a code graph was built at the commit the caller expects? (#21327)

Four outcomes and only one of them is "current": a graph with no provenance record is
``unknown`` and a caller who stated no expectation gets ``unchecked``. Neither may read as fresh.
Kept free of heavy imports so request models and tool schemas can use ``COMMIT_PATTERN``.
"""

import re
from typing import Any

#: Shape of a commit a caller may state it expects; abbreviations are allowed.
COMMIT_PATTERN = r"^[0-9a-fA-F]{7,40}$"
_COMMIT_RE = re.compile(COMMIT_PATTERN)


def commits_agree(indexed: str, expected: str) -> bool:
    """True when *expected* (full or abbreviated) names the commit the graph was built at."""
    if not _COMMIT_RE.match(expected):
        raise ValueError("expected_commit must be 7 to 40 hexadecimal characters")
    indexed, expected = indexed.lower(), expected.lower()
    return indexed.startswith(expected) or expected.startswith(indexed)


def freshness_of(indexed_at_commit: str | None, expected_commit: str | None) -> dict[str, Any]:
    """The staleness fields of an answer. ``stale`` is True/False only when it was actually decided."""
    if expected_commit is None:
        return {"freshness": "unchecked", "stale": None, "expected_commit": None}
    if not indexed_at_commit:
        return {"freshness": "unknown", "stale": None, "expected_commit": expected_commit}
    agree = commits_agree(indexed_at_commit, expected_commit)
    return {"freshness": "current" if agree else "stale", "stale": not agree, "expected_commit": expected_commit}
