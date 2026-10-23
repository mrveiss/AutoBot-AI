# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as _ssot_config

# Re-export async utilities for convenient imports
from utils.async_chromadb_client import (
    AsyncChromaClient,
    AsyncChromaCollection,
    get_async_chromadb_client,
    wrap_collection_async,
)
from utils.chromadb_auth import chroma_client_auth_kwargs
from utils.chromadb_store_repairs import prepare_local_store

if TYPE_CHECKING:
    import chromadb  # noqa: F401

logger = get_logger(__name__)

# Issue #3094: Use SSOT config port so the default (8100) matches Ansible deployment.
#
# Host comes from the SSOT too, and its default is `127.0.0.1` -- so an empty host,
# and therefore the local PersistentClient branch below, requires
# `AUTOBOT_CHROMADB_HOST` to be set to an empty value *explicitly*. An unset
# variable yields the default and takes the HttpClient branch.
#
# This comment previously read "Host remains os.getenv-based: empty string = use
# local PersistentClient (dev mode)", which had been true of an earlier revision and
# describes the opposite default. Three sessions diagnosing empty analytics panels on
# 2026-09-27 read it, concluded the backend was opening an empty local store because
# no host appears in any config file, and were wrong: the host is a code default, not
# a config value. A stale comment about a mechanism outranks the mechanism for anyone
# who stops reading at the comment (#17646 review).
_CHROMADB_HOST = _ssot_config.vm.chromadb
_CHROMADB_PORT = _ssot_config.port.chromadb
# Issue #12513: whether server auth (CHROMA_SERVER_AUTHN_*) is configured.
# Folded into the client cache key so a deploy that later sets the token
# rebuilds the client instead of reusing a pre-auth cached instance.
_CHROMADB_AUTH_ENABLED = bool(_ssot_config.misc.chromadb_auth_token)

# Module-level client cache (singleton per key) — mirrors _async_client_cache so
# the sync client isn't rebuilt, and legacy migrations re-run, on every call (#10601).
# Key: (endpoint_or_path, allow_reset, anonymized_telemetry, auth_enabled) — #10625/
# #12513 fold the settings into the key so a different-settings request builds
# the right client.
_sync_client_cache: Dict[Tuple[str, bool, bool, bool], Any] = {}

# Module exports
__all__ = [
    "get_chromadb_client",
    "get_async_chromadb_client",
    "get_all_paginated",
    "get_backend_client",
    "AsyncChromaClient",
    "AsyncChromaCollection",
    "wrap_collection_async",
]


_local_open_lock = threading.RLock()  # guards the client cache; the repair locks live in chromadb_store_repairs


def _open_local_client(cache_key: tuple, chroma_path: Path, allow_reset: bool, telemetry: bool) -> Any:
    """Prepare the store, then open (or reuse) the cached local PersistentClient."""
    import chromadb  # noqa: F811
    from chromadb.config import Settings as ChromaSettings

    with _local_open_lock:
        cached = _sync_client_cache.get(cache_key)
        if cached is not None:
            return cached
        prepare_local_store(chroma_path)
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(allow_reset=allow_reset, anonymized_telemetry=telemetry),
        )
        logger.info("ChromaDB persistent client at: %s", chroma_path)
        _sync_client_cache[cache_key] = client
        return client


def get_chromadb_client(
    db_path: str = "",
    allow_reset: bool = False,
    anonymized_telemetry: bool = False,
) -> Any:
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
    # Issue #3016: lazy import — chromadb is heavy (~1s import)
    import chromadb  # noqa: F811
    from chromadb.config import Settings as ChromaSettings

    # #10601: return the cached client instead of rebuilding it (and re-running
    # the legacy migrations below) on every call. Mirrors _async_client_cache.
    cache_key = (
        f"http://{_CHROMADB_HOST}:{_CHROMADB_PORT}" if _CHROMADB_HOST else (db_path or "data/chromadb"),
        allow_reset,
        anonymized_telemetry,
        _CHROMADB_AUTH_ENABLED,
    )
    cached = _sync_client_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        if _CHROMADB_HOST:
            client = chromadb.HttpClient(
                host=_CHROMADB_HOST,
                port=_CHROMADB_PORT,
                settings=ChromaSettings(
                    anonymized_telemetry=anonymized_telemetry,
                    **chroma_client_auth_kwargs(),
                ),
            )
            logger.info(
                "ChromaDB HTTP client connected to %s:%s",
                _CHROMADB_HOST,
                _CHROMADB_PORT,
            )
            _sync_client_cache[cache_key] = client
            return client

        # Fallback: local PersistentClient (shared with the async client, #18789)
        client = _open_local_client(cache_key, Path(db_path or "data/chromadb"), allow_reset, anonymized_telemetry)
        return client

    except Exception as e:
        logger.error("Failed to initialize ChromaDB client: %s", e)
        raise


def get_all_paginated(
    collection,
    where=None,
    include=None,
    page_size: int = 500,
) -> dict:
    """Fetch all matching documents from a ChromaDB collection using pagination.

    ChromaDB's SQLite backend hard-limits SQL variables to 999, which is
    exceeded by unbounded collection.get() on large collections. This helper
    pages through results with limit+offset to avoid that constraint. #1361.

    Args:
        collection: A ChromaDB Collection object.
        where: Optional metadata filter dict (same as Collection.get where).
        include: Fields to include (e.g. ["metadatas"]). Defaults to ["metadatas"].
        page_size: Items per page. Default 500 (safely under the 999 limit).

    Returns:
        Dict with merged results in the same shape as Collection.get():
        {"ids": [...], "metadatas": [...], ...}
    """
    if include is None:
        include = ["metadatas"]

    merged: dict = {}
    offset = 0
    while True:
        page = collection.get(
            where=where,
            limit=page_size,
            offset=offset,
            include=include,
        )
        if not merged:
            merged = {k: list(v) if v is not None else [] for k, v in page.items()}
        else:
            for key, values in page.items():
                if values:
                    merged[key].extend(values)
        ids = page.get("ids") or []
        if len(ids) < page_size:
            break
        offset += page_size
    return merged


def get_backend_client(
    db_path: str = "",
    allow_reset: bool = False,
    anonymized_telemetry: bool = False,
) -> Any:
    """Return a backend-agnostic ``BaseClient`` wrapping the ChromaDB client.

    Issue #5062: opt-in seam for callers that want to target the
    ``knowledge.backends.BaseClient`` ABC instead of ChromaDB directly.
    Existing callers keep using ``get_chromadb_client`` unchanged.

    Args match ``get_chromadb_client``; see that function for semantics.
    """
    # Lazy import to keep the backends package optional at import time.
    from knowledge.backends.chromadb_adapter import ChromaDBClient

    raw = get_chromadb_client(
        db_path=db_path,
        allow_reset=allow_reset,
        anonymized_telemetry=anonymized_telemetry,
    )
    return ChromaDBClient(raw)
