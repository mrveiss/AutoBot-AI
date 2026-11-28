# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one reader of a collection's HNSW settings (#18143).

ChromaDB holds the distance space and index parameters in the collection's CONFIGURATION. They are also
written to ``metadata`` as ``hnsw:*`` at creation, but a metadata ``modify`` cannot carry them and drops
them from ``collection.metadata`` (the configuration keeps them in force). A reader of the metadata keys
alone therefore reports "unknown" after any metadata modify, such as an embedding-space stamp. Every
reader of a collection's HNSW settings goes through :func:`hnsw_params`.
"""

from __future__ import annotations

from typing import Any, Dict

#: reported name -> (ChromaDB configuration key under ["hnsw"], legacy metadata key, value when neither holds it)
_SETTINGS = {
    "space": ("space", "hnsw:space", "unknown"),
    "construction_ef": ("ef_construction", "hnsw:construction_ef", "default"),
    "search_ef": ("ef_search", "hnsw:search_ef", "default"),
    "M": ("max_neighbors", "hnsw:M", "default"),
}


def _configured(collection: Any) -> Dict[str, Any]:
    raw = getattr(collection, "_raw", collection)
    config = getattr(collection, "configuration", None) or getattr(raw, "configuration", None) or {}
    try:
        return dict(config.get("hnsw") or {})
    except AttributeError:
        return {}


def hnsw_params(collection: Any) -> Dict[str, Any]:
    """space / construction_ef / search_ef / M of ``collection``: configuration first, then metadata."""
    configured = _configured(collection)
    raw = getattr(collection, "_raw", collection)
    metadata = getattr(collection, "metadata", None) or getattr(raw, "metadata", None) or {}
    return {
        name: configured.get(key, metadata.get(legacy, missing)) for name, (key, legacy, missing) in _SETTINGS.items()
    }


def configuration_from_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """The configuration ChromaDB derives from ``hnsw:*`` creation metadata (used by the in-memory backend)."""
    return {"hnsw": {key: metadata[legacy] for key, legacy, _ in _SETTINGS.values() if legacy in metadata}}
