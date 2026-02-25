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
import os
from pathlib import Path
from typing import TYPE_CHECKING, Union

import chromadb
from chromadb.config import Settings as ChromaSettings

# Re-export async utilities for convenient imports
from utils.async_chromadb_client import (
    AsyncChromaClient,
    AsyncChromaCollection,
    get_async_chromadb_client,
    wrap_collection_async,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Remote ChromaDB config — set AUTOBOT_CHROMADB_HOST to enable HTTP client
_CHROMADB_HOST = os.getenv("AUTOBOT_CHROMADB_HOST", "")
_CHROMADB_PORT = int(os.getenv("AUTOBOT_CHROMADB_PORT", "8000"))

# Module exports
__all__ = [
    "get_chromadb_client",
    "get_async_chromadb_client",
    "AsyncChromaClient",
    "AsyncChromaCollection",
    "wrap_collection_async",
]


def get_chromadb_client(
    db_path: str = "",
    allow_reset: bool = False,
    anonymized_telemetry: bool = False,
) -> Union[chromadb.HttpClient, chromadb.PersistentClient]:
    """
    Create a ChromaDB client with consistent configuration.

    Uses remote HttpClient when AUTOBOT_CHROMADB_HOST is set, otherwise
    falls back to local PersistentClient for development.

    Args:
        db_path: Path for local PersistentClient (ignored when remote)
        allow_reset: Whether to allow database resets (default: False)
        anonymized_telemetry: Whether to enable telemetry (default: False)

    Returns:
        Configured ChromaDB client (Http or Persistent)
    """
    try:
        if _CHROMADB_HOST:
            client = chromadb.HttpClient(
                host=_CHROMADB_HOST,
                port=_CHROMADB_PORT,
                settings=ChromaSettings(
                    anonymized_telemetry=anonymized_telemetry,
                ),
            )
            logger.info(
                "ChromaDB HTTP client connected to %s:%s",
                _CHROMADB_HOST,
                _CHROMADB_PORT,
            )
            return client

        # Fallback: local PersistentClient
        chroma_path = Path(db_path or "data/chromadb")
        chroma_path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(
                allow_reset=allow_reset,
                anonymized_telemetry=anonymized_telemetry,
            ),
        )
        logger.info("ChromaDB persistent client at: %s", chroma_path)
        return client

    except Exception as e:
        logger.error("Failed to initialize ChromaDB client: %s", e)
        raise
