# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Utilities

Shared helper functions for knowledge base operations.
"""

import json
from typing import Any, Dict

# Issue #380: Module-level tuples for type checking
_SEQUENCE_TYPES = (list, tuple)
_CHROMADB_ALLOWED_TYPES = (str, int, float, type(None))


def sanitize_metadata_for_chromadb(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize metadata for ChromaDB compatibility.

    ChromaDB only allows metadata values of type: str, int, float, None.
    This function converts lists/arrays to comma-separated strings.

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
            # Convert arrays to comma-separated strings
            sanitized[key] = ", ".join(str(v) for v in value)
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
