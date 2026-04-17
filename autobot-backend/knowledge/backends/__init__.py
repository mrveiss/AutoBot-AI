# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pluggable vector-store backends (Issue #5062).

Public API:
    * ``BaseCollection`` / ``BaseClient`` — ABCs every backend implements.
    * ``ChromaDBCollection`` / ``ChromaDBClient`` — production adapter wrapping
      the existing ChromaDB client from ``utils/chromadb_client.py``.
    * ``InMemoryCollection`` / ``InMemoryClient`` — dependency-free adapter
      used in unit tests.
    * ``get_default_client`` — returns a ``BaseClient`` pointing at the current
      environment's default backend (ChromaDB today).
"""

from __future__ import annotations

from knowledge.backends.base import (
    BaseClient,
    BaseCollection,
    Embedding,
    Metadata,
    Where,
    WhereDocument,
)
from knowledge.backends.chromadb_adapter import ChromaDBClient, ChromaDBCollection
from knowledge.backends.memory_adapter import InMemoryClient, InMemoryCollection


def get_default_client(**kwargs) -> BaseClient:
    """Return a ``BaseClient`` for the current default backend.

    Today this always wraps ChromaDB via the existing ``utils.chromadb_client``
    construction path, so all HNSW / sqlite migrations (#1390, #2735) still
    run. Forwarded kwargs match ``utils.chromadb_client.get_chromadb_client``.
    """
    # Lazy import: utils/chromadb_client does heavy sqlite migration work
    # on first call, and importing it eagerly from this package-init would
    # slow down every `from knowledge.backends import ...` in tests.
    from utils.chromadb_client import get_chromadb_client

    return ChromaDBClient(get_chromadb_client(**kwargs))


__all__ = [
    "BaseCollection",
    "BaseClient",
    "ChromaDBClient",
    "ChromaDBCollection",
    "Embedding",
    "InMemoryClient",
    "InMemoryCollection",
    "Metadata",
    "Where",
    "WhereDocument",
    "get_default_client",
]
