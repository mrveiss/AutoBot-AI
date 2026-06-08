# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Evolutionary lineage service — ancestor traversal, best-ancestor selection,
entity version history, and rollback.

Issue #4681: Provides the query API over the parent→child chain recorded in
SynthesisProvenanceLog and ChromaDB entity metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, parse_utc_iso

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# SynthesisRun dataclass
# ---------------------------------------------------------------------------


@dataclass
class SynthesisRun:
    """One node in the synthesis lineage tree.

    Issue #4681: Stores every field needed by the autonomous loop (#4680) to
    select the best parent for the next hypothesis generation.
    """

    run_id: str
    parent_run_id: str | None
    prompt_variant: str
    source_doc_ids: List[str]
    output_summary_id: str
    score: float
    timestamp: datetime
    collection_name: str

    @classmethod
    def from_provenance_entry(cls, entry: Dict[str, Any]) -> "SynthesisRun":
        """Build a SynthesisRun from a deserialized provenance log entry.

        Handles entries written before #4681 (missing new fields) gracefully.
        """
        ran_at_raw = entry.get("ran_at", "")
        try:
            ts = parse_utc_iso(ran_at_raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            ts = now_utc()

        synthesis_ids: List[str] = entry.get("synthesis_ids") or []
        output_id = synthesis_ids[0] if synthesis_ids else entry.get("run_id", "")

        return cls(
            run_id=entry.get("run_id", ""),
            parent_run_id=entry.get("parent_run_id") or None,
            prompt_variant=entry.get("prompt_variant") or entry.get("prompt_template", ""),
            source_doc_ids=entry.get("source_doc_ids") or entry.get("source_docs") or [],
            output_summary_id=output_id,
            score=float(entry.get("score", 0.0)),
            timestamp=ts,
            collection_name=entry.get("collection_name", ""),
        )


# ---------------------------------------------------------------------------
# LineageService
# ---------------------------------------------------------------------------


class LineageService:
    """Query API for synthesis lineage and ChromaDB entity version history.

    Issue #4681: All methods are async; storage is ChromaDB for entity history
    and Redis stream (via SynthesisProvenanceLog) for synthesis runs.
    """

    def __init__(self, provenance_log: Any, chromadb_collection_factory: Any) -> None:
        """
        Args:
            provenance_log: SynthesisProvenanceLog instance.
            chromadb_collection_factory: Async callable(collection_name) → AsyncCollection.
        """
        self._provenance_log = provenance_log
        self._collection_factory = chromadb_collection_factory

    # ------------------------------------------------------------------
    # Synthesis lineage
    # ------------------------------------------------------------------

    async def get_ancestors(self, run_id: str, depth: int = 10) -> List[SynthesisRun]:
        """Traverse the parent→child chain up to *depth* steps.

        Starts from *run_id* and walks backwards through parent_run_id links.
        Returns the chain from oldest ancestor to *run_id* (inclusive).

        Args:
            run_id: The run to start from.
            depth: Maximum number of ancestor hops to follow.

        Returns:
            List of SynthesisRun from oldest ancestor to run_id, inclusive.
        """
        chain: List[SynthesisRun] = []
        current_id: str | None = run_id
        seen: set = set()
        for _ in range(depth + 1):
            if current_id is None or current_id in seen:
                break
            entry = await self._provenance_log.get_by_run_id(current_id)
            if entry is None:
                break
            run = SynthesisRun.from_provenance_entry(entry)
            seen.add(current_id)
            chain.append(run)
            current_id = run.parent_run_id
        chain.reverse()
        return chain

    async def get_best_ancestor(self, collection: str, metric: str = "score") -> SynthesisRun | None:
        """Return the highest-scoring run in the lineage tree for *collection*.

        Uses ``get_best_run_id_for_collection()`` for O(1) sorted-set lookup
        followed by a single ``get_by_run_id()`` hash fetch — replacing the
        O(total_runs) full-stream scan.  Falls back to None when no runs exist.

        Issue #4788: O(1) ancestor lookup via Redis sorted set index.

        Args:
            collection: ChromaDB collection name to filter by.
            metric: Field to maximise (currently only "score" supported).

        Returns:
            The SynthesisRun with the highest metric value, or None when no
            runs exist for the collection.
        """
        best_run_id = await self._provenance_log.get_best_run_id_for_collection(collection)
        if not best_run_id:
            return None
        entry = await self._provenance_log.get_by_run_id(best_run_id)
        if entry is None:
            return None
        return SynthesisRun.from_provenance_entry(entry)

    # ------------------------------------------------------------------
    # Entity version history (ChromaDB)
    # ------------------------------------------------------------------

    async def get_entity_history(self, entity_id: str) -> List[Dict[str, Any]]:
        """Return version list for a ChromaDB entity.

        Queries the ``kb_entity_history`` collection for all records whose
        ``entity_id`` matches.  Records are sorted ascending by version.

        Args:
            entity_id: ChromaDB ID of the entity.

        Returns:
            List of version dicts with at minimum: entity_id, lineage_version,
            lineage_source_run_id, score, timestamp.
        """
        try:
            collection = await self._collection_factory("kb_entity_history")
            results = await collection.get(
                where={"entity_id": entity_id},
                include=["metadatas", "documents"],
            )
        except Exception:
            logger.exception("get_entity_history: query failed for entity '%s'", entity_id)
            return []

        if not results or not results.get("ids"):
            return []

        versions: List[Dict[str, Any]] = []
        ids = results["ids"]
        metadatas = results.get("metadatas") or [{}] * len(ids)
        documents = results.get("documents") or [""] * len(ids)
        for idx, vid in enumerate(ids):
            meta = metadatas[idx] if idx < len(metadatas) else {}
            doc = documents[idx] if idx < len(documents) else ""
            versions.append(
                {
                    "version_id": vid,
                    "entity_id": entity_id,
                    "content": doc,
                    **meta,
                }
            )
        versions.sort(key=lambda v: int(v.get("lineage_version", 0)))
        return versions

    async def rollback_entity(self, entity_id: str, to_version: int) -> None:
        """Restore a ChromaDB entity to a prior version.

        Fetches the requested version from ``kb_entity_history`` and upserts
        it back into the live collection identified by ``lineage_source_collection``
        in the version metadata.  Increments ``lineage_version`` by 1 so the
        rollback itself is auditable.

        Args:
            entity_id: ChromaDB ID of the entity to roll back.
            to_version: Target lineage_version number.

        Raises:
            ValueError: When the requested version does not exist.
        """
        history = await self.get_entity_history(entity_id)
        target = next(
            (v for v in history if int(v.get("lineage_version", -1)) == to_version),
            None,
        )
        if target is None:
            raise ValueError(f"No version {to_version} found for entity '{entity_id}'")

        source_collection = target.get("lineage_source_collection", "")
        if not source_collection:
            raise ValueError(f"Version {to_version} has no lineage_source_collection — cannot roll back")

        live_collection = await self._collection_factory(source_collection)
        await self._get_current_version(entity_id, live_collection)
        new_version = max(int(v.get("lineage_version", 0)) for v in history) + 1
        rollback_meta = {k: v for k, v in target.items() if k not in ("version_id", "content")}
        rollback_meta["lineage_version"] = new_version
        rollback_meta["lineage_parent_id"] = target["version_id"]
        rollback_meta["lineage_rollback_from"] = to_version

        content = target.get("content", "")
        await live_collection.upsert(
            ids=[entity_id],
            documents=[content],
            metadatas=[rollback_meta],
        )
        logger.info(
            "Rolled back entity '%s' to version %d (new version=%d)",
            entity_id,
            to_version,
            new_version,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def stamp_entity_version(
        self,
        entity_id: str,
        content: str,
        metadata: Dict[str, Any],
        source_run_id: str,
        source_collection: str,
    ) -> None:
        """Append a version snapshot to ``kb_entity_history``.

        Called by KBSynthesizer / DocIndexerService after every upsert so the
        full history of changes is preserved and ``rollback_entity()`` can work.

        Args:
            entity_id: ChromaDB ID of the entity being versioned.
            content: Document content at this version.
            metadata: Current entity metadata (will be augmented with lineage fields).
            source_run_id: synthesis run that created/updated this entity.
            source_collection: Collection where the live entity lives.
        """
        try:
            history = await self.get_entity_history(entity_id)
            next_version = max((int(v.get("lineage_version", 0)) for v in history), default=0) + 1
            parent_version_id = history[-1]["version_id"] if history else None

            version_id = f"{entity_id}_v{next_version}"
            version_meta = {
                **metadata,
                "entity_id": entity_id,
                "lineage_version": next_version,
                "lineage_source_run_id": source_run_id,
                "lineage_source_collection": source_collection,
                "lineage_parent_id": parent_version_id or "",
            }

            history_collection = await self._collection_factory("kb_entity_history")
            await history_collection.upsert(
                ids=[version_id],
                documents=[content],
                metadatas=[version_meta],
            )
            logger.debug("Stamped entity '%s' version %d (run=%s)", entity_id, next_version, source_run_id)
        except Exception:
            logger.exception("stamp_entity_version: failed for entity '%s' (non-fatal)", entity_id)

    async def _get_current_version(self, entity_id: str, collection: Any) -> List[Dict]:
        """Return current metadata list for entity_id from *collection*."""
        try:
            result = await collection.get(ids=[entity_id], include=["metadatas"])
            return result.get("metadatas") or []
        except Exception:
            return []


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_lineage_service: LineageService | None = None


def get_lineage_service(provenance_log: Any, chromadb_collection_factory: Any) -> LineageService:
    """Return the singleton LineageService, creating it if needed."""
    global _lineage_service
    if _lineage_service is None:
        _lineage_service = LineageService(provenance_log, chromadb_collection_factory)
    return _lineage_service
