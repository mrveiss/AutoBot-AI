# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Call-site lines carried by one call edge (#21317).

One edge per ``(scope, target)`` keeps every line the call appears on, up to
``MAX_CALL_SITES_PER_EDGE``; the calls beyond the cap are counted in
``dropped_call_sites`` rather than silently lost. ChromaDB metadata must be scalar, so the list
is stored as a JSON string (``call_lines``) and ``decode_edge_metadata`` is the one decoder
every reader of edge records goes through.
"""

import json
from typing import Any

from autobot_shared.env_utils import env_int_clamped

MAX_CALL_SITES_PER_EDGE = env_int_clamped("AUTOBOT_CODE_INDEX_MAX_CALL_SITES_PER_EDGE", 50, 1, 10000)


def add_call_site(edge: dict, line: int) -> None:
    """Append *line* to *edge*'s call sites, or count it as dropped once the cap is reached."""
    if len(edge["lines"]) < MAX_CALL_SITES_PER_EDGE:
        edge["lines"].append(line)
    else:
        edge["dropped_call_sites"] += 1


def call_site_metadata(edge: dict) -> dict[str, Any]:
    """Scalar metadata for an extracted edge's call sites.

    ``call_line`` stays the first site, for readers of records written before ``call_lines`` existed.
    """
    lines = edge.get("lines") or []
    return {
        "call_line": lines[0] if lines else 0,
        "call_lines": json.dumps(lines, separators=(",", ":")),
        "dropped_call_sites": edge.get("dropped_call_sites", 0),
    }


def _decode_lines(meta: dict) -> list[int]:
    try:
        decoded = json.loads(meta["call_lines"])
    except (KeyError, TypeError, ValueError):
        decoded = None
    if isinstance(decoded, list):
        return [n for n in decoded if isinstance(n, int)]
    legacy = meta.get("call_line")  # a record written before call_lines existed carries one site
    return [legacy] if isinstance(legacy, int) and legacy > 0 else []


def decode_edge_metadata(meta: dict) -> dict[str, Any]:
    """A copy of an edge record's metadata with ``call_lines`` as a list of ints (never the JSON string)."""
    return {**meta, "call_lines": _decode_lines(meta)}
