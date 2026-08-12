# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Relations Mixin

Issue #1279: Provides fact-to-fact relation storage for the KnowledgeBase,
enabling graph-based knowledge retrieval alongside vector search.

Relations are stored in Redis using the same pattern as
autobot_memory_graph.relations (outgoing/incoming JSON lists), but scoped
to knowledge-base facts (key prefix ``kb:rel:``).

Relation types are imported from
``autobot_memory_graph.core.CORE_RELATION_TYPES`` — the single canonical
vocabulary (Issue #13452). This module no longer keeps its own copy.
"""

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from autobot_memory_graph.core import (
    CORE_RELATION_TYPES,
    canonical_relation_filter,
    canonical_relation_type,
    relation_type_matches,
)
from autobot_shared.error_boundaries import error_boundary
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Issue #13452: derived from the canonical vocabulary instead of restating it.
# This module's docstring always claimed the types came from
# autobot_memory_graph, but the list below was an independent copy that spelled
# the general relation "relates_to" where the memory graph spelled it
# "related_to" — a divergence that silently dropped edges (#13367).
#
# Facts relate to facts, so the knowledge base takes CORE_RELATION_TYPES and
# not the identity/activity names (owns, has_secret, ...) that only make sense
# between memory-graph entities.
KB_RELATION_TYPES: Set[str] = set(CORE_RELATION_TYPES)


class RelationsMixin:
    """
    Mixin providing fact-to-fact relation operations for KnowledgeBase.

    Requires ``self._aioredis_client`` (async Redis) and ``self.redis_client``
    (sync Redis) from KnowledgeBaseCore.
    """

    RELATION_TYPES = KB_RELATION_TYPES

    # -- helpers ----------------------------------------------------------

    # #13452: the one matcher, shared with autobot_memory_graph so the two
    # stores cannot drift in how they resolve a legacy spelling.
    _relation_type_matches = staticmethod(relation_type_matches)

    def _rel_out_key(self, fact_id: str) -> str:
        return f"kb:rel:out:{fact_id}"

    def _rel_in_key(self, fact_id: str) -> str:
        return f"kb:rel:in:{fact_id}"

    async def _fact_exists(self, fact_id: str) -> bool:
        """Check whether a fact key exists in Redis."""
        return bool(await self.redis().exists(f"fact:{fact_id}"))

    async def _get_fact_content(self, fact_id: str) -> dict | None:
        """Return decoded fact hash or None."""
        raw = await self.redis().hgetall(f"fact:{fact_id}")
        if not raw:
            return None
        decoded = {}
        for k, v in raw.items():
            key = k.decode("utf-8") if isinstance(k, bytes) else k
            val = v.decode("utf-8") if isinstance(v, bytes) else v
            decoded[key] = val
        decoded["id"] = fact_id
        return decoded

    # -- CRUD -------------------------------------------------------------

    async def create_fact_relation(
        self,
        source_fact_id: str,
        target_fact_id: str,
        relation_type: str,
        metadata: dict | None = None,
    ) -> Dict[str, Any]:
        """Create a relation between two knowledge-base facts."""
        self.ensure_initialized()

        # #13452: accept the legacy "relates_to" spelling and store the
        # canonical "related_to", so existing API clients keep working while
        # only one spelling is ever written.
        relation_type = canonical_relation_type(relation_type)
        if relation_type not in KB_RELATION_TYPES:
            return {
                "success": False,
                "message": (f"Invalid relation_type '{relation_type}'. " f"Valid: {sorted(KB_RELATION_TYPES)}"),
            }

        src_exists, tgt_exists = await asyncio.gather(
            self._fact_exists(source_fact_id),
            self._fact_exists(target_fact_id),
        )
        if not src_exists:
            return {
                "success": False,
                "message": f"Source fact not found: {source_fact_id}",
            }
        if not tgt_exists:
            return {
                "success": False,
                "message": f"Target fact not found: {target_fact_id}",
            }

        ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        out_entry = {
            "to": target_fact_id,
            "type": relation_type,
            "created_at": ts,
            "metadata": metadata or {},
        }
        in_entry = {
            "from": source_fact_id,
            "type": relation_type,
            "created_at": ts,
        }

        out_key = self._rel_out_key(source_fact_id)
        in_key = self._rel_in_key(target_fact_id)

        pipe = self.redis().pipeline()
        pipe.rpush(out_key, json.dumps(out_entry))
        pipe.rpush(in_key, json.dumps(in_entry))
        await pipe.execute()

        logger.info(
            "KB relation created: %s --[%s]--> %s",
            source_fact_id[:8],
            relation_type,
            target_fact_id[:8],
        )
        return {"success": True, "relation": out_entry}

    async def delete_fact_relation(
        self,
        source_fact_id: str,
        target_fact_id: str,
        relation_type: str | None = None,
    ) -> Dict[str, Any]:
        """Delete relation(s) between two facts."""
        self.ensure_initialized()

        removed = 0
        # Filter outgoing
        out_key = self._rel_out_key(source_fact_id)
        raw_out = await self.redis().lrange(out_key, 0, -1)
        if raw_out:
            kept = []
            for entry_bytes in raw_out:
                entry = json.loads(entry_bytes)
                if entry["to"] == target_fact_id and self._relation_type_matches(entry["type"], relation_type):
                    removed += 1
                else:
                    kept.append(entry_bytes)
            await self.redis().delete(out_key)
            if kept:
                await self.redis().rpush(out_key, *kept)

        # Filter incoming
        in_key = self._rel_in_key(target_fact_id)
        raw_in = await self.redis().lrange(in_key, 0, -1)
        if raw_in:
            kept = []
            for entry_bytes in raw_in:
                entry = json.loads(entry_bytes)
                if entry["from"] == source_fact_id and self._relation_type_matches(entry["type"], relation_type):
                    pass  # drop
                else:
                    kept.append(entry_bytes)
            await self.redis().delete(in_key)
            if kept:
                await self.redis().rpush(in_key, *kept)

        if removed == 0:
            return {
                "success": False,
                "message": "No matching relation found",
            }
        return {"success": True, "removed": removed}

    async def get_fact_relations(
        self,
        fact_id: str,
        direction: str = "both",
        relation_type: str | None = None,
        include_fact_details: bool = False,
    ) -> Dict[str, Any]:
        """Get relations for a fact."""
        self.ensure_initialized()

        relations: List[Dict[str, Any]] = []

        if direction in ("outgoing", "both"):
            raw = await self.redis().lrange(self._rel_out_key(fact_id), 0, -1)
            for entry_bytes in raw:
                entry = json.loads(entry_bytes)
                if not self._relation_type_matches(entry["type"], relation_type):
                    continue
                rel = {
                    "from": fact_id,
                    "to": entry["to"],
                    "type": entry["type"],
                    "direction": "outgoing",
                    "metadata": entry.get("metadata", {}),
                }
                if include_fact_details:
                    rel["target_fact"] = await self._get_fact_content(entry["to"])
                relations.append(rel)

        if direction in ("incoming", "both"):
            raw = await self.redis().lrange(self._rel_in_key(fact_id), 0, -1)
            for entry_bytes in raw:
                entry = json.loads(entry_bytes)
                if not self._relation_type_matches(entry["type"], relation_type):
                    continue
                rel = {
                    "from": entry["from"],
                    "to": fact_id,
                    "type": entry["type"],
                    "direction": "incoming",
                }
                if include_fact_details:
                    rel["source_fact"] = await self._get_fact_content(entry["from"])
                relations.append(rel)

        return {"success": True, "fact_id": fact_id, "relations": relations}

    # -- traversal --------------------------------------------------------

    async def traverse_relations(
        self,
        start_fact_id: str,
        max_depth: int = 2,
        relation_types: List[str] | None = None,
        include_fact_details: bool = False,
    ) -> Dict[str, Any]:
        """BFS traversal of fact-relation graph."""
        self.ensure_initialized()

        if not await self._fact_exists(start_fact_id):
            return {
                "success": False,
                "message": f"Start fact not found: {start_fact_id}",
            }

        visited: set = set()
        queue: list = [(start_fact_id, 0)]
        nodes: list = []
        edges: list = []
        # #13452: canonicalise the filter once so legacy-spelled stored edges match.
        wanted = canonical_relation_filter(relation_types)

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)

            if include_fact_details:
                fact = await self._get_fact_content(current_id)
                if fact:
                    nodes.append(fact)

            if depth >= max_depth:
                continue

            raw = await self.redis().lrange(self._rel_out_key(current_id), 0, -1)
            for entry_bytes in raw:
                entry = json.loads(entry_bytes)
                if wanted is not None and canonical_relation_type(entry["type"]) not in wanted:
                    continue
                edges.append(
                    {
                        "from": current_id,
                        "to": entry["to"],
                        "type": entry["type"],
                    }
                )
                if entry["to"] not in visited:
                    queue.append((entry["to"], depth + 1))

        return {
            "success": True,
            "start_fact_id": start_fact_id,
            "nodes_visited": len(visited),
            "nodes": nodes if include_fact_details else [],
            "edges": edges,
        }

    # -- hybrid search ----------------------------------------------------

    async def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        expand_relations: bool = True,
        relation_depth: int = 1,
        relation_types: List[str] | None = None,
    ) -> Dict[str, Any]:
        """Combine vector search with graph-relation expansion."""
        self.ensure_initialized()

        # Step 1: vector search via existing SearchMixin
        vector_results = await self.search(query, top_k=top_k)

        if not expand_relations:
            return {
                "success": True,
                "vector_results": vector_results,
                "graph_expanded": [],
            }

        # Step 2: expand each result through relations
        seen_ids: set = set()
        for r in vector_results:
            fid = r.get("id") or r.get("fact_id")
            if fid:
                seen_ids.add(fid)

        graph_expanded: list = []
        for seed_id in list(seen_ids):
            traversal = await self.traverse_relations(
                start_fact_id=seed_id,
                max_depth=relation_depth,
                relation_types=relation_types,
                include_fact_details=True,
            )
            if traversal.get("success"):
                for node in traversal.get("nodes", []):
                    nid = node.get("id")
                    if nid and nid not in seen_ids:
                        seen_ids.add(nid)
                        graph_expanded.append(node)

        return {
            "success": True,
            "vector_results": vector_results,
            "graph_expanded": graph_expanded,
        }

    # -- stats ------------------------------------------------------------

    @error_boundary(component="knowledge", function="get_relation_stats")
    async def get_relation_stats(self) -> Dict[str, Any]:
        """Aggregate statistics about fact relations."""
        self.ensure_initialized()

        total = 0
        by_type: Dict[str, int] = defaultdict(int)

        cursor = b"0"
        while True:
            cursor, keys = await self.redis().scan(cursor=cursor, match="kb:rel:out:*", count=200)
            for key in keys:
                raw = await self.redis().lrange(key, 0, -1)
                for entry_bytes in raw:
                    entry = json.loads(entry_bytes)
                    total += 1
                    # #13452: bucket under the canonical name, otherwise a
                    # legacy "relates_to" row surfaces as a bucket that is
                    # absent from the available_types list returned alongside it.
                    by_type[canonical_relation_type(entry["type"])] += 1
            if cursor == b"0" or cursor == 0:
                break

        return {
            "success": True,
            "total_relations": total,
            "by_type": dict(by_type),
            "available_types": sorted(KB_RELATION_TYPES),
        }
