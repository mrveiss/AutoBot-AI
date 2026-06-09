# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Pluggable vector-store backends (Issue #5062, async seam #5316).

Public API:
    * ``BaseCollection`` / ``BaseClient`` — sync ABCs every backend implements.
    * ``AsyncBaseCollection`` / ``AsyncBaseClient`` — async-native ABCs.
    * ``ChromaDBCollection`` / ``ChromaDBClient`` — sync production adapter.
    * ``AsyncChromaDBCollection`` / ``AsyncChromaDBClient`` — async adapter.
    * ``InMemoryCollection`` / ``InMemoryClient`` — sync in-memory test adapter.
    * ``AsyncInMemoryCollection`` / ``AsyncInMemoryClient`` — async test adapter.
    * ``get_default_client`` — sync ``BaseClient`` for the current backend.
    * ``get_async_default_client`` — async ``AsyncBaseClient`` for the current backend.
"""

from __future__ import annotations

from knowledge.backends.async_base import AsyncBaseClient, AsyncBaseCollection
from knowledge.backends.async_chromadb_adapter import (
    AsyncChromaDBClient,
    AsyncChromaDBCollection,
)
from knowledge.backends.async_memory_adapter import (
    AsyncInMemoryClient,
    AsyncInMemoryCollection,
)
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


async def get_async_default_client(**kwargs) -> AsyncBaseClient:
    """Return an ``AsyncBaseClient`` for the current default backend (#5316).

    Forwarded kwargs match ``utils.async_chromadb_client.get_async_chromadb_client``.
    Use this from async contexts instead of ``get_default_client`` to avoid
    blocking the event loop on ChromaDB calls.
    """
    from utils.async_chromadb_client import get_async_chromadb_client

    return AsyncChromaDBClient(await get_async_chromadb_client(**kwargs))


__all__ = [
    "AsyncBaseClient",
    "AsyncBaseCollection",
    "AsyncChromaDBClient",
    "AsyncChromaDBCollection",
    "AsyncInMemoryClient",
    "AsyncInMemoryCollection",
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
    "get_async_default_client",
    "get_default_client",
]
