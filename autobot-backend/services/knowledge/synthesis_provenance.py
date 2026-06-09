# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Synthesis provenance log — records each KnowledgeSynthesizer run to a Redis stream.

Issue #4567: Add synthesis provenance log so operators can audit which source
documents and LLM models produced which insight IDs.
Issue #4681: Extended with parent_run_id, source_doc_ids, prompt_variant for
evolutionary lineage tracking.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

_STREAM_KEY = "kb:synthesis:log"
_RUN_KEY_PREFIX = "kb:synthesis:run:"
_COLLECTION_BEST_KEY_PREFIX = "kb:synthesis:best:"


class SynthesisProvenanceLog:
    """Append-only provenance log for KnowledgeSynthesizer runs."""

    async def log_run(
        self,
        run_id: str,
        source_docs: List[str],
        synthesis_ids: List[str],
        llm_model: str,
        prompt_template: str,
        duration_ms: int,
        parent_run_id: str | None = None,
        source_doc_ids: List[str] | None = None,
        prompt_variant: str | None = None,
        score: float = 0.0,
        collection_name: str | None = None,
    ) -> None:
        """Append a provenance entry to the Redis stream.

        Args:
            run_id: Unique identifier for this synthesis run.
            source_docs: List of source document file paths used as input.
            synthesis_ids: List of insight/synthesis IDs produced.
            llm_model: Name/identifier of the LLM model used.
            prompt_template: Name or key of the prompt template used.
            duration_ms: Total synthesis duration in milliseconds.
            parent_run_id: ID of the prior synthesis run this evolved from (#4681).
            source_doc_ids: ChromaDB IDs of input documents (#4681).
            prompt_variant: Prompt variant identifier used for this run (#4681).
            score: Quality score for this run (0.0–1.0) (#4681).
            collection_name: Target ChromaDB collection name (#4681).
        """
        entry: Dict[str, Any] = {
            "run_id": run_id,
            "source_docs": json.dumps(source_docs),
            "synthesis_ids": json.dumps(synthesis_ids),
            "llm_model": llm_model,
            "prompt_template": prompt_template,
            "ran_at": now_utc().isoformat(),
            "duration_ms": str(duration_ms),
            "parent_run_id": parent_run_id or "",
            "source_doc_ids": json.dumps(source_doc_ids or source_docs),
            "prompt_variant": prompt_variant or prompt_template,
            "score": str(score),
            "collection_name": collection_name or "",
        }
        try:
            redis = await get_async_redis_client(database="main")
            pipe = redis.pipeline()
            pipe.xadd(_STREAM_KEY, entry)
            pipe.hset(f"{_RUN_KEY_PREFIX}{run_id}", mapping=entry)
            if collection_name:
                pipe.zadd(
                    f"{_COLLECTION_BEST_KEY_PREFIX}{collection_name}",
                    {run_id: score},
                )
            await pipe.execute()
            logger.debug("Provenance logged for run %s (%d insights)", run_id, len(synthesis_ids))
        except Exception:
            logger.exception("Failed to write provenance log for run %s", run_id)

    async def get_by_run_id(self, run_id: str) -> Dict[str, Any] | None:
        """Return the provenance entry for a single run by its ID.

        Uses a Redis hash key (O(1)) instead of scanning the full stream.
        Returns None when the run does not exist.

        Issue #4788: replaces O(total_runs) stream scan in get_ancestors().
        """
        try:
            redis = await get_async_redis_client(database="main")
            raw = await redis.hgetall(f"{_RUN_KEY_PREFIX}{run_id}")
        except Exception:
            logger.exception("get_by_run_id: Redis error for run_id '%s'", run_id)
            return None

        if not raw:
            return None

        entry = {
            k.decode("utf-8") if isinstance(k, bytes) else k: (v.decode("utf-8") if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }
        for list_field in ("source_docs", "synthesis_ids", "source_doc_ids"):
            if list_field in entry:
                try:
                    entry[list_field] = json.loads(entry[list_field])
                except (json.JSONDecodeError, TypeError):
                    entry[list_field] = []
        if "duration_ms" in entry:
            try:
                entry["duration_ms"] = int(entry["duration_ms"])
            except (ValueError, TypeError):
                pass
        if "score" in entry:
            try:
                entry["score"] = float(entry["score"])
            except (ValueError, TypeError):
                entry["score"] = 0.0
        entry.setdefault("parent_run_id", None)
        if entry["parent_run_id"] == "":
            entry["parent_run_id"] = None
        entry.setdefault("prompt_variant", entry.get("prompt_template", ""))
        entry.setdefault("collection_name", "")
        return entry

    async def get_best_run_id_for_collection(self, collection_name: str) -> str | None:
        """Return the run_id with the highest score for *collection_name*.

        Uses the ``kb:synthesis:best:{collection_name}`` sorted set for an O(1)
        lookup instead of scanning the full stream.  Returns None when no runs
        exist for the collection.

        Issue #4788: O(1) replacement for the 500-entry scan in get_best_ancestor.
        """
        try:
            redis = await get_async_redis_client(database="main")
            results = await redis.zrevrange(f"{_COLLECTION_BEST_KEY_PREFIX}{collection_name}", 0, 0)
        except Exception:
            logger.exception(
                "get_best_run_id_for_collection: Redis error for collection '%s'",
                collection_name,
            )
            return None

        if not results:
            return None
        raw = results[0]
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    async def get_best_prompt_variant(
        self,
        collection_name: str,
        limit: int = 50,
    ) -> str:
        """Return the prompt variant with the highest average score for a collection.

        Reads the most recent provenance entries, filters to those whose
        ``prompt_template`` matches ``collection_name``, then returns the
        ``prompt_variant`` with the highest mean score.  Returns an empty
        string when no scored history exists (cold-start).

        Issue #4675.

        Args:
            collection_name: The collection name used as ``prompt_template`` key.
            limit: Maximum number of recent entries to consider.
        """
        entries = await self.get_recent(limit=limit)
        # Accumulate scores per variant for this collection.
        variant_scores: Dict[str, List[float]] = {}
        for entry in entries:
            if entry.get("prompt_template") != collection_name:
                continue
            variant = str(entry.get("prompt_variant", ""))
            if not variant or variant == collection_name:
                # Skip entries where variant == base template name (not a named variant).
                continue
            score = float(entry.get("score", 0.0))
            variant_scores.setdefault(variant, []).append(score)

        if not variant_scores:
            return ""

        best = max(variant_scores, key=lambda v: sum(variant_scores[v]) / len(variant_scores[v]))
        return best

    async def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent provenance entries.

        Args:
            limit: Maximum number of entries to return (newest first).

        Returns:
            List of provenance dicts with deserialized fields.
        """
        try:
            redis = await get_async_redis_client(database="main")
            raw_entries = await redis.xrevrange(_STREAM_KEY, count=limit)
        except Exception:
            logger.exception("Failed to read provenance log")
            return []

        results = []
        for _entry_id, fields in raw_entries:
            entry = {
                k.decode("utf-8") if isinstance(k, bytes) else k: (v.decode("utf-8") if isinstance(v, bytes) else v)
                for k, v in fields.items()
            }
            for list_field in ("source_docs", "synthesis_ids", "source_doc_ids"):
                if list_field in entry:
                    try:
                        entry[list_field] = json.loads(entry[list_field])
                    except (json.JSONDecodeError, TypeError):
                        entry[list_field] = []
            if "duration_ms" in entry:
                try:
                    entry["duration_ms"] = int(entry["duration_ms"])
                except (ValueError, TypeError):
                    pass
            if "score" in entry:
                try:
                    entry["score"] = float(entry["score"])
                except (ValueError, TypeError):
                    entry["score"] = 0.0
            # Normalize optional lineage fields introduced in #4681
            entry.setdefault("parent_run_id", None)
            if entry["parent_run_id"] == "":
                entry["parent_run_id"] = None
            entry.setdefault("prompt_variant", entry.get("prompt_template", ""))
            entry.setdefault("collection_name", "")
            results.append(entry)
        return results
