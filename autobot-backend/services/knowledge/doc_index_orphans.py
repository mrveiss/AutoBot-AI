# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Drop a re-indexed file's stale chunks only after its new chunks are stored (#17530).

Chunk ids hash the section name, so a renamed section leaves an orphan. Deleting the
file's rows *before* embedding lost the old rows whenever an embed failed; instead the
old ids are read first and only those the new run did not rewrite are removed.
"""

import asyncio
import uuid
from typing import Any, Callable, Iterable, List, Set

from autobot_shared.logging_manager import get_logger
from knowledge.chunk_identity import DOC_ID_LENGTH, doc_chunk_id

logger = get_logger(__name__)

BASE_ID_LENGTH = DOC_ID_LENGTH
chunk_base_id = doc_chunk_id  # the one definition lives in knowledge.chunk_identity (#18142)


def _ids_for(collection: Any, rel_path: str, run_token: str | None = None) -> Set[str]:
    """Ids of the file's rows; with *run_token*, only the rows that run wrote."""
    got = collection.get(where={"file_path": rel_path}, include=["metadatas"])
    ids = got.get("ids") or []
    metas = got.get("metadatas") or [{}] * len(ids)
    return {i for i, m in zip(ids, metas) if run_token is None or (m or {}).get("index_run") == run_token}


def existing_ids(collection: Any, rel_path: str) -> Set[str]:
    """Ids currently stored for *rel_path* (read before the re-index starts)."""
    return _ids_for(collection, rel_path)


async def drop_stale_chunks(
    collection: Any, rel_path: str, old_ids: Set[str], run_token: str, failed_bases: Iterable[str]
) -> int:
    """Delete old ids this run did not rewrite, sparing those of chunks whose embed failed."""
    written = await asyncio.to_thread(_ids_for, collection, rel_path, run_token)
    spared = set(failed_bases)
    stale: List[str] = [i for i in old_ids - written if i[:BASE_ID_LENGTH] not in spared]
    if stale:
        await asyncio.to_thread(collection.delete, ids=stale)
        logger.info("Dropped %d stale chunk(s) of %s", len(stale), rel_path)
    return len(stale)


async def reindex_file(
    collection: Any,
    index_chunk: Callable[..., bool],
    chunks: List[dict],
    rel_path: str,
    file_tags: List[str],
    tier: int,
) -> int:
    """Index every chunk of *rel_path*, then drop its stale rows; returns how many chunks were stored."""
    old_ids = await asyncio.to_thread(existing_ids, collection, rel_path)
    run_token, indexed, failed = uuid.uuid4().hex, 0, []
    for i, chunk in enumerate(chunks):
        if await asyncio.to_thread(index_chunk, chunk, i, len(chunks), rel_path, file_tags, tier, run_token):
            indexed += 1
        else:
            failed.append(chunk_base_id(rel_path, chunk["section"], i))
    await drop_stale_chunks(collection, rel_path, old_ids, run_token, failed)
    return indexed
