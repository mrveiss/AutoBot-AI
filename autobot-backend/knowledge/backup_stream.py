# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Write a knowledge backup batch by batch, so its vectors never sit in memory together (#19994).

The file is the same JSON document a backup has always been, so restore reads old and new alike. It
is written beside its final name and moved there only when whole: a failure leaves no half backup.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from knowledge.backup_embeddings import EXPORT_BATCH_SIZE

logger = get_logger(__name__)


def _open_for_write(path: str, compression: bool):
    return gzip.open(path, "wt", encoding="utf-8") if compression else open(path, "w", encoding="utf-8")


def _discard(out, partial: str) -> None:
    out.close()
    if os.path.exists(partial):
        os.unlink(partial)


def _fsync_path(path: str) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _commit(out, partial: str, backup_file: str) -> None:
    """Make the whole file durable before its final name can point at it, then the name itself."""
    out.close()  # flushes, and for gzip writes the trailer
    _fsync_path(partial)
    os.replace(partial, backup_file)
    _fsync_path(os.path.dirname(backup_file) or ".")


def _document_head(backup_data: Dict[str, Any]) -> str:
    """The document up to its facts; ``_build_backup_data`` always sets the header's fields, so it is never empty."""
    header = {key: value for key, value in backup_data.items() if key != "facts"}
    return json.dumps(header, ensure_ascii=False, indent=2)[:-2] + ',\n  "facts": ['


async def _batch_text(kb, batch: List[Dict[str, Any]], with_vectors: bool, first: bool) -> str:
    """One batch of the facts array, its vectors read here and dropped once written."""
    vectors: Dict[str, Dict[str, Any]] = {}
    if with_vectors:
        try:
            vectors = await kb._fetch_embeddings_from_vector_store([f["fact_id"] for f in batch if f.get("fact_id")])
        except Exception as e:
            logger.warning("Could not retrieve embeddings: %s", e)
    merged = [{**fact, **vectors.get(fact.get("fact_id"), {})} for fact in batch]
    text = await asyncio.to_thread(lambda: ",\n".join(json.dumps(f, ensure_ascii=False) for f in merged))
    return ("\n" if first else ",\n") + text


async def write_backup(kb, backup_file: str, backup_data: Dict[str, Any], compression: bool) -> None:
    """Write *backup_data* to *backup_file*; its facts gain their vectors only as each batch is written."""
    facts = backup_data["facts"]
    with_vectors = backup_data["include_embeddings"] and getattr(kb, "vector_store", None) is not None
    partial = f"{backup_file}.partial"
    out = await asyncio.to_thread(_open_for_write, partial, compression)
    try:
        await asyncio.to_thread(out.write, _document_head(backup_data))
        for start in range(0, len(facts), EXPORT_BATCH_SIZE):
            text = await _batch_text(kb, facts[start : start + EXPORT_BATCH_SIZE], with_vectors, start == 0)
            await asyncio.to_thread(out.write, text)
        await asyncio.to_thread(out.write, "\n  ]\n}\n")
        await asyncio.to_thread(_commit, out, partial, backup_file)
    except BaseException:
        await asyncio.to_thread(_discard, out, partial)
        raise
