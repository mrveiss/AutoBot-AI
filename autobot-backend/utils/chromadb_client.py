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

import json
import logging
import os
import sqlite3
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


def _migrate_legacy_collection_configs(chroma_path: Path) -> None:
    """Migrate ChromaDB collections missing _type in config_json_str.

    ChromaDB 0.5.x requires '_type' fields in collection config JSON.
    Collections created by older versions store config_json_str as '{}',
    which causes KeyError: '_type' on access. This patches the SQLite
    database directly before the PersistentClient opens it.
    """
    db_file = chroma_path / "chroma.sqlite3"
    if not db_file.exists():
        return

    try:
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, config_json_str FROM collections")
        rows = cursor.fetchall()

        fixed = 0
        for cid, name, config_str in rows:
            config = json.loads(config_str) if config_str else {}
            if "_type" in config:
                continue

            # Read HNSW metadata stored by the old version
            cursor.execute(
                "SELECT key, str_value, int_value, float_value "
                "FROM collection_metadata WHERE collection_id=?",
                (cid,),
            )
            hnsw = {}
            for key, sv, iv, fv in cursor.fetchall():
                if key.startswith("hnsw:"):
                    hnsw[key[5:]] = (
                        sv if sv is not None else (iv if iv is not None else fv)
                    )

            new_cfg = json.dumps(
                {
                    "hnsw_configuration": {
                        "space": hnsw.get("space", "l2"),
                        "ef_construction": hnsw.get("construction_ef", 100),
                        "ef_search": hnsw.get("search_ef", 10),
                        "num_threads": 4,
                        "M": hnsw.get("M", 16),
                        "resize_factor": 1.2,
                        "batch_size": 100,
                        "sync_threshold": 1000,
                        "_type": "HNSWConfigurationInternal",
                    },
                    "_type": "CollectionConfigurationInternal",
                }
            )
            cursor.execute(
                "UPDATE collections SET config_json_str=? WHERE id=?",
                (new_cfg, cid),
            )
            fixed += 1

        if fixed:
            conn.commit()
            logger.info(
                "Migrated %d ChromaDB collection config(s) " "to 0.5.x format",
                fixed,
            )
        conn.close()
    except Exception as e:
        logger.warning("ChromaDB config migration check failed: %s", e)


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
        _migrate_legacy_collection_configs(chroma_path)
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
