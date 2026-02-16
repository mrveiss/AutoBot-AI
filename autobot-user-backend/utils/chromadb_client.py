# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Reusable ChromaDB Client Initialization

Provides centralized functions for creating ChromaDB clients with
consistent configuration across the entire codebase.

Includes both synchronous and asynchronous client support:
- get_chromadb_client(): Synchronous client (legacy support)
- get_async_chromadb_client(): Async client (recommended for async code)
- AsyncChromaCollection: Async wrapper for collections
- AsyncChromaClient: Async wrapper for client operations

For async contexts (FastAPI endpoints, async functions), always use the
async variants to prevent event loop blocking. See Issue #369.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import chromadb
from chromadb.config import Settings as ChromaSettings

# Re-export async utilities for convenient imports
from backend.utils.async_chromadb_client import (
    AsyncChromaClient,
    AsyncChromaCollection,
    get_async_chromadb_client,
    wrap_collection_async,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Module exports
__all__ = [
    "get_chromadb_client",
    "get_async_chromadb_client",
    "AsyncChromaClient",
    "AsyncChromaCollection",
    "wrap_collection_async",
]


def get_chromadb_client(
    db_path: str, allow_reset: bool = False, anonymized_telemetry: bool = False
) -> chromadb.PersistentClient:
    """
    Create a ChromaDB persistent client with consistent configuration.

    Args:
        db_path: Path to the ChromaDB database directory
        allow_reset: Whether to allow database resets (default: False)
        anonymized_telemetry: Whether to enable telemetry (default: False)

    Returns:
        Configured ChromaDB PersistentClient

    Raises:
        Exception: If client initialization fails
    """
    try:
        # Ensure directory exists
        chroma_path = Path(db_path)
        chroma_path.mkdir(parents=True, exist_ok=True)

        # Create persistent client with standardized settings
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(
                allow_reset=allow_reset, anonymized_telemetry=anonymized_telemetry
            ),
        )

        logger.info("ChromaDB client initialized at: %s", chroma_path)
        return client

    except Exception as e:
        logger.error("Failed to initialize ChromaDB client: %s", e)
        raise
