# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Utilities

Shared helper functions for knowledge base operations.
"""

import json
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Issue #380: Module-level tuples for type checking
_SEQUENCE_TYPES = (list, tuple)
_CHROMADB_ALLOWED_TYPES = (str, int, float, type(None))


def _encode_sequence(key: str, value: Any) -> str:
    """Encode a list/tuple for ChromaDB without losing structure (#14257).

    A list of scalars keeps the historical comma-joined form: that is what every
    caller before #13894 passed, it is what is already stored, and changing it
    would make existing metadata unreadable.

    A list containing anything structured is JSON-encoded instead — the same
    treatment a bare ``dict`` has always had. Joining those with ``str()``
    produced a Python repr that ``json.loads`` rejects and no split can undo,
    because the commas *inside* each element are indistinguishable from the
    commas *between* them:

        [{"page": 1, "start": 0}]  ->  "{'page': 1, 'start': 0}"

    The write succeeded and the read returned a string, so nothing failed; the
    structure was simply gone. An encoder that accepts input it cannot represent
    and reports success is the same shape as a guard that reports clean on input
    it could not read.
    """
    if all(isinstance(item, _CHROMADB_ALLOWED_TYPES) for item in value):
        return ", ".join(str(item) for item in value)
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        # Not JSON-serialisable either. `str()` is the only remaining option, so
        # say so rather than letting the caller believe the value round-trips.
        logger.warning(
            "Metadata %r holds a sequence that is neither scalar nor JSON-serialisable; "
            "storing its repr, which cannot be parsed back.",
            key,
        )
        return str(value)


def sanitize_metadata_for_chromadb(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize metadata for ChromaDB compatibility.

    ChromaDB only allows metadata values of type: str, int, float, None.
    Lists of scalars become comma-separated strings; anything structured is
    JSON-encoded so it survives the round trip (#14257).

    Args:
        metadata: Original metadata dict that may contain arrays

    Returns:
        Sanitized metadata dict with all arrays converted to strings
    """
    if not metadata:
        return {}

    sanitized = {}
    for key, value in metadata.items():
        if isinstance(value, _SEQUENCE_TYPES):  # Issue #380
            sanitized[key] = _encode_sequence(key, value)
        elif isinstance(value, dict):
            # Convert dicts to JSON strings
            sanitized[key] = json.dumps(value)
        elif isinstance(value, _CHROMADB_ALLOWED_TYPES):  # Issue #380
            # Allowed types - keep as is
            sanitized[key] = value
        else:
            # Convert other types to string
            sanitized[key] = str(value)

    return sanitized


# Backward compatibility alias
_sanitize_metadata_for_chromadb = sanitize_metadata_for_chromadb
