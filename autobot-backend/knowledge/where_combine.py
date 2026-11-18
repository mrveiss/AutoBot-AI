# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one place a vector-store ``where`` is AND-combined (#18946).

Dependency-free so both ``knowledge.quarantine`` and ``knowledge.search_filters`` can import it
without a cycle. Nothing else builds a ``{"$and": [...]}``; a caller's filter is always combined
through :func:`and_where`, so it can only narrow what is served.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def and_where(*clauses: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """AND the given ``where`` clauses.

    ``None`` and empty clauses are dropped; an input that is already ``{"$and": [...]}`` is
    flattened rather than nested. One surviving clause is returned unwrapped, none gives ``None``.
    """
    flat: list = []
    for clause in clauses:
        if not clause:
            continue
        inner = clause.get("$and") if len(clause) == 1 else None
        flat.extend(inner if isinstance(inner, list) else [clause])
    if not flat:
        return None
    return flat[0] if len(flat) == 1 else {"$and": flat}
