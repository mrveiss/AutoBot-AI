# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The documentation browser's read side: one entry per indexed document (#18129).

``DocIndexerService`` is the only writer of documentation, into the ``autobot_docs``
collection, one row per chunk. The browser (``/docs/browse``, ``/docs/categories``,
``/docs/stats``) reads the SAME collection and groups its rows by ``file_path``; there is no
second index (the retired standalone indexer mirrored a ``doc_hash:*`` entry per file into
Redis, which nothing writes any more).
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List

from services.knowledge.doc_taxonomy import detect_category


def group_indexed_documents(metadatas: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fold chunk metadata into one dict per document, keyed by ``file_path``.

    ``category`` is the taxonomy id (the vocabulary of ``DocIndexerService``'s ``--category``
    filter and of ``/docs/categories``), not the chunk's directory name. ``content_hash`` is a
    stable per-document id derived from the path; the frontend keys rows on it.
    """
    docs: Dict[str, Dict[str, Any]] = {}
    for meta in metadatas:
        file_path = (meta or {}).get("file_path")
        if not file_path:
            continue
        doc = docs.get(file_path)
        if doc is None:
            doc = docs[file_path] = {
                "file_path": file_path,
                "title": meta.get("title") or "",
                "category": detect_category(Path(file_path)),
                "doc_type": meta.get("doc_type") or "",
                "tier": meta.get("tier") or "",
                "chunks": 0,
                "indexed_at": None,
                "content_hash": hashlib.md5(file_path.encode("utf-8"), usedforsecurity=False).hexdigest(),
            }
        doc["chunks"] += 1
        indexed_at = meta.get("indexed_at")
        if indexed_at and (doc["indexed_at"] is None or indexed_at > doc["indexed_at"]):
            doc["indexed_at"] = indexed_at
    return list(docs.values())


async def list_indexed_documents(service: Any) -> List[Dict[str, Any]]:
    """Every indexed document in the service's collection; ``[]`` when it has none.

    Raises ``RuntimeError`` when the service cannot initialise, so an endpoint can answer 503
    instead of presenting an unreachable index as an empty one.
    """
    if not service._initialized and not await service.initialize():
        raise RuntimeError("documentation index unavailable")
    from utils.chromadb_client import get_all_paginated

    page = await asyncio.to_thread(get_all_paginated, service._collection, None, ["metadatas"])
    return group_indexed_documents((page or {}).get("metadatas") or [])
