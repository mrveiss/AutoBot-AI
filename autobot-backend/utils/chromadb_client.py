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
import pickle  # nosec B403 — reading ChromaDB internal pickle files only
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
    "get_all_paginated",
    "AsyncChromaClient",
    "AsyncChromaCollection",
    "wrap_collection_async",
    "_fix_hnsw_pickle_format",
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


def _fix_segment_hnsw_space(chroma_path: Path) -> None:
    """Copy hnsw:space from collection_metadata into segment_metadata.

    ChromaDB 0.5.23 stores hnsw:space in collection_metadata but reads
    it from segment_metadata when initializing the HNSW segment. If
    segment_metadata is empty the space defaults to L2, producing wrong
    distances even though the collection was created with cosine (#1390).
    """
    db_file = chroma_path / "chroma.sqlite3"
    if not db_file.exists():
        return
    try:
        conn = sqlite3.connect(str(db_file))
        c = conn.cursor()

        # Find vector segments whose collection has hnsw:space set
        c.execute(
            "SELECT s.id, cm.str_value "
            "FROM segments s "
            "JOIN collection_metadata cm "
            "  ON cm.collection_id = s.collection "
            "WHERE s.scope = 'VECTOR' "
            "  AND cm.key = 'hnsw:space' "
            "  AND cm.str_value IS NOT NULL"
        )
        rows = c.fetchall()

        fixed = 0
        for seg_id, space_val in rows:
            # Check if segment_metadata already has hnsw:space
            c.execute(
                "SELECT 1 FROM segment_metadata "
                "WHERE segment_id = ? AND key = 'hnsw:space'",
                (seg_id,),
            )
            if c.fetchone():
                continue
            c.execute(
                "INSERT INTO segment_metadata "
                "(segment_id, key, str_value) "
                "VALUES (?, 'hnsw:space', ?)",
                (seg_id, space_val),
            )
            fixed += 1

        if fixed:
            conn.commit()
            logger.info("Propagated hnsw:space to %d segment(s)", fixed)
        conn.close()
    except Exception as e:
        logger.warning("segment hnsw:space fix failed: %s", e)


def _fix_seq_id_blob_type(chroma_path: Path) -> None:
    """Fix embeddings.seq_id BLOB->INTEGER for ChromaDB 0.5.x (#1390).

    ChromaDB 0.5.23 creates seq_id as BLOB but its Rust compactor
    expects INTEGER. Patch the column type before the compactor starts.
    """
    db_file = chroma_path / "chroma.sqlite3"
    if not db_file.exists():
        return
    try:
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(embeddings)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        if cols.get("seq_id", "").upper() != "BLOB":
            conn.close()
            return
        cursor.execute(
            "CREATE TABLE embeddings_fix ("
            "id INTEGER PRIMARY KEY, "
            "segment_id TEXT NOT NULL, "
            "embedding_id TEXT NOT NULL, "
            "seq_id INTEGER NOT NULL, "
            "created_at TIMESTAMP NOT NULL DEFAULT "
            "CURRENT_TIMESTAMP, "
            "UNIQUE (segment_id, embedding_id))"
        )
        cursor.execute("INSERT INTO embeddings_fix SELECT * FROM embeddings")
        cursor.execute("DROP TABLE embeddings")
        cursor.execute("ALTER TABLE embeddings_fix RENAME TO embeddings")
        conn.commit()
        conn.close()
        logger.info("Fixed embeddings.seq_id BLOB->INTEGER")
    except Exception as e:
        logger.warning("seq_id fix failed: %s", e)


def _infer_hnsw_dimensionality(segment_dir: Path) -> int:
    """Infer HNSW embedding dimensionality from binary files (#1390).

    Reads data_level0.bin size and element count to compute the
    vector dimension via hnswlib's internal record layout.
    Returns 0 if inference fails.
    """
    import struct

    data_file = segment_dir / "data_level0.bin"
    header_file = segment_dir / "header.bin"
    if not data_file.exists() or not header_file.exists():
        return 0
    try:
        file_size = data_file.stat().st_size
        with open(header_file, "rb") as f:
            hdr = f.read(52)
        vals = struct.unpack("<" + "I" * 13, hdr[:52])
        count = vals[5]
        if count == 0:
            return 0
        rec_size = file_size // count
        links_size = vals[11]
        label_size = 8
        dim = (rec_size - links_size - label_size) // 4
        if 64 <= dim <= 4096:
            return dim
    except Exception:
        pass
    return 0


def _fix_hnsw_pickle_format(chroma_path: Path) -> None:
    """Fix HNSW index_metadata.pickle for ChromaDB 0.5.x (#1390).

    ChromaDB 0.5.23 may serialize HNSW metadata as a plain dict
    (reader expects PersistentData) and/or leave dimensionality
    as None (HNSW init requires an int). This patches both.
    """
    try:
        from chromadb.segment.impl.vector.local_persistent_hnsw import PersistentData
    except ImportError:
        return

    for pkl_file in chroma_path.glob("*/index_metadata.pickle"):
        try:
            with open(pkl_file, "rb") as f:
                data = pickle.load(f)  # nosec B301
            needs_fix = isinstance(data, dict)
            if isinstance(data, dict):
                dim = data.get("dimensionality")
            else:
                dim = getattr(data, "dimensionality", None)
            needs_dim_fix = dim is None
            if not needs_fix and not needs_dim_fix:
                continue
            if needs_dim_fix:
                dim = _infer_hnsw_dimensionality(pkl_file.parent)
                if dim == 0:
                    dim = None
            if isinstance(data, dict):
                obj = PersistentData(
                    dimensionality=dim,
                    total_elements_added=data.get("total_elements_added", 0),
                    id_to_label=data.get("id_to_label", {}),
                    label_to_id=data.get("label_to_id", {}),
                    id_to_seq_id=data.get("id_to_seq_id", {}),
                )
            else:
                obj = data
                obj.dimensionality = dim
            with open(pkl_file, "wb") as f:
                pickle.dump(obj, f)
            logger.info(
                "Fixed HNSW pickle: %s (dim=%s)",
                pkl_file.parent.name[:8],
                dim,
            )
        except Exception as e:
            logger.warning("HNSW pickle fix failed for %s: %s", pkl_file, e)


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
        _fix_segment_hnsw_space(chroma_path)
        _fix_seq_id_blob_type(chroma_path)
        _fix_hnsw_pickle_format(chroma_path)
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
