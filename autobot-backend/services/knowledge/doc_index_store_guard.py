# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Decide when the doc indexer may re-embed everything, and say why (#20886).

An empty collection used to mean "re-embed every file". It can also mean the indexer opened a
different store than the one the previous run filled (a local path versus the server). The count
cannot tell the two apart, so the store each run embedded into is recorded beside the hash cache
and a changed store with a non-empty cache is refused, never silently re-embedded. A count that
cannot be read is likewise refused, never read as zero. Nothing here deletes or rewrites vectors.
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from autobot_shared.env_registry import env
from autobot_shared.logging_manager import get_logger
from services.knowledge.index_cache_paths import doc_index_store

logger = get_logger(__name__)

# Seconds between batch progress lines from the embed loop.
PROGRESS_INTERVAL_MIN_S, PROGRESS_INTERVAL_MAX_S = 1.0, 3600.0


def clamp_progress_interval(seconds: float) -> float:
    """The registry declares 1-3600 s but does not enforce it; 0 would log once per chunk."""
    return min(max(float(seconds), PROGRESS_INTERVAL_MIN_S), PROGRESS_INTERVAL_MAX_S)


EMBED_PROGRESS_INTERVAL_S = clamp_progress_interval(env("AUTOBOT_DOC_INDEX_PROGRESS_INTERVAL_S"))
# Sent with every embedding request so the embedding server can attribute the load.
CALLER_HEADER = "X-AutoBot-Caller"


class CollectionCountUnknown(RuntimeError):
    """The collection's vector count could not be read, so emptiness is unknown."""


class StoreLocationChanged(RuntimeError):
    """The collection is empty because the indexer opened a different store than last time."""


def read_count(collection: Any) -> int:
    """The collection's vector count; an unreadable count raises, it is never zero."""
    try:
        return int(collection.count())
    except Exception as e:
        raise CollectionCountUnknown(f"cannot read the collection's vector count: {e}") from e


def load_recorded_store(hash_override: Path | None = None) -> str | None:
    """The store the last successful run embedded into, or None when never recorded."""
    path = doc_index_store(hash_override)
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("store")
    except (OSError, ValueError, AttributeError):
        return None


def write_recorded_store(store: str, hash_override: Path | None = None) -> None:
    """Record the store; an unwritable record raises OSError (the adoption command must not report success)."""
    path = doc_index_store(hash_override)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"store": store}), encoding="utf-8")


def save_recorded_store(store: str, hash_override: Path | None = None) -> None:
    """Record the store this run embedded into; a failed write is logged, the run itself stands."""
    try:
        write_recorded_store(store, hash_override)
    except OSError as e:
        logger.warning("Could not record the doc index store: %s", e)


def _refusal(cache_entries: int, recorded: str | None, current: str) -> str:
    """The refusal text: what was seen and the two ways to proceed (#20886)."""
    seen = (
        f"was built against '{recorded}' and this run opened '{current}'"
        if recorded
        else f"predates store recording and this run opened '{current}'"
    )
    return (
        f"collection is empty but the hash cache ({cache_entries} files) {seen}. Refusing to re-embed "
        "into what may be the wrong store. Point the indexer at the original store, or pass --force to "
        "re-embed everything here on purpose, or pass --adopt-store to record this store as the cache's "
        "store without embedding anything."
    )


def adopt_store(store: str, collection: Any, hash_override: Path | None = None) -> str:
    """Operator command (--adopt-store): record *store*; embeds and deletes nothing.

    The count is read first, so an unreachable store raises before the previous record is touched, and
    an unwritable record raises instead of reporting success.
    """
    vectors = read_count(collection)
    write_recorded_store(store, hash_override)
    logger.info("Doc index store adopted: '%s' (%d vectors); nothing embedded", store, vectors)
    return store


def _moved_refusal(cache_entries: int, recorded: str, current: str) -> str:
    """The refusal text for a populated collection that is not the store the cache was built against."""
    return (
        f"the hash cache ({cache_entries} files) was built against '{recorded}' and this run opened '{current}'. "
        "Incremental mode would skip every cached document this store lacks. Point the indexer at the original "
        "store, or pass --force to re-embed everything here on purpose, or pass --adopt-store to record this "
        "store as the cache's store without embedding anything."
    )


def reindex_reason(
    *, count: int, needs_reindex: bool, cache_entries: int, hash_override: Path | None, current: str
) -> str | None:
    """Why a full re-embed is warranted, or None. Raises StoreLocationChanged rather than guess."""
    if needs_reindex:
        return "collection was recreated after an embedding-dimension mismatch (_needs_reindex)"
    recorded = load_recorded_store(hash_override)
    if count != 0:
        if recorded is None:  # a legacy cache over a populated collection: no re-embed risk, so remember the store
            save_recorded_store(current, hash_override)
        elif cache_entries and recorded != current:
            raise StoreLocationChanged(_moved_refusal(cache_entries, recorded, current))
        return None
    if cache_entries and recorded != current:
        raise StoreLocationChanged(_refusal(cache_entries, recorded, current))
    return f"collection count=0 ({cache_entries} files in the hash cache, store '{current}')"


async def open_store_for_adoption(root_dir: Path, collection_name: str) -> tuple[str, Any]:
    """The configured store and its EXISTING collection, for --adopt-store (#20886).

    Unlike service initialisation this probes no embedding dimension and can neither create nor
    recreate a collection, so adopting a store never changes what it holds.
    """
    from knowledge.backends import get_default_client
    from utils.chromadb_client import chromadb_endpoint

    path = str(root_dir / "data" / "chromadb")
    client = await asyncio.to_thread(get_default_client, db_path=path)
    collection = await asyncio.to_thread(client.get_collection, collection_name)
    return chromadb_endpoint(path), collection


def log_run_summary(result: Any, collection: Any) -> None:
    """One closing line: outcome counts, elapsed time and the collection's size."""
    logger.info(
        "Documentation indexing complete: %d success, %d failed, %d skipped in %.1fs (collection now has %d vectors)",
        result.success,
        result.failed,
        result.skipped,
        result.elapsed_seconds,
        collection.count() if collection else 0,
    )


def log_run_start(embed_model: str | None, ollama_url: str) -> None:
    """One line that says who is about to embed, and with what."""
    import sys

    logger.info(
        "Doc indexer start: pid=%d ppid=%d argv=%s embed_model=%s ollama=%s",
        os.getpid(),
        os.getppid(),
        sys.argv,
        embed_model,
        ollama_url,
    )


def caller_tag() -> dict[str, str]:
    """Headers identifying this process to the embedding server."""
    return {CALLER_HEADER: f"doc_indexer pid={os.getpid()}"}


class EmbedProgress:
    """Rate-limited batch progress for the embed loop."""

    def __init__(self, interval_s: float = EMBED_PROGRESS_INTERVAL_S) -> None:
        self._interval = interval_s
        self._count = 0
        self._last = self._start = time.monotonic()

    @property
    def count(self) -> int:
        """Chunks embedded so far."""
        return self._count

    def tick(self) -> None:
        """Count one embedded chunk; log at most once per interval."""
        self._count += 1
        now = time.monotonic()
        if now - self._last >= self._interval:
            self._last = now
            logger.info("Doc indexer embedding: %d chunks in %.0fs", self._count, now - self._start)


def log_file_progress(index: int, total: int, rel_path: str, chunks: int, started: float) -> None:
    """One line per indexed file: position, path, chunks embedded, seconds elapsed."""
    logger.info("Doc indexer %d/%d %s chunks=%d elapsed=%.1fs", index, total, rel_path, chunks, time.time() - started)
