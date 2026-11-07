# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge-graph sections: every ChromaDB knowledge bucket mapped to one graph section (#20945).

``BUCKET_SECTIONS`` is the single registry of which store appears in the knowledge graph. A
collection the registry neither maps nor explicitly excludes is *unmapped*; a guard test fails on
any unmapped collection that holds data, so a new bucket cannot silently stay out of the graph.
Chat conversations and query caches are not KB buckets (maintainer decision 2026-11-06).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from knowledge.index_embedding_space import (
    ACCELERATOR_COLLECTIONS,
    CODE_INDEX,
    PATTERN_INDEXES,
)
from llc.kb.collections import KbCollectionManager

logger = get_logger(__name__)

# Records sampled per section; the response reports total vs returned so the cap is never silent.
SECTION_SAMPLE_LIMIT = int(os.getenv("AUTOBOT_KB_GRAPH_SECTION_SAMPLE_LIMIT", "25"))
SECTION_PREVIEW_CHARS = int(os.getenv("AUTOBOT_KB_GRAPH_PREVIEW_CHARS", "160"))


@dataclass(frozen=True)
class BucketSection:
    """One graph section: the exact collection names and name prefixes that feed it."""

    key: str
    label: str
    names: Tuple[str, ...] = ()
    prefixes: Tuple[str, ...] = ()
    admin_only: bool = False  # per-entity buckets carry no per-record owner: fail closed (#16665)

    def matches(self, collection: str) -> bool:
        return collection in self.names or any(collection.startswith(p + ":") for p in self.prefixes)


_P = KbCollectionManager
BUCKET_SECTIONS: Tuple[BucketSection, ...] = (
    BucketSection("docs", "Documentation", names=("autobot_docs",)),
    BucketSection("memory", "Memory", names=("autobot_memory",)),
    BucketSection("code", "Code analysis", names=("autobot_code", CODE_INDEX, *PATTERN_INDEXES, "code_kb")),
    BucketSection("verbatim", "Verbatim and synthesis", names=("autobot_verbatim", "autobot_synthesis_architecture")),
    BucketSection("embeddings", "Media embeddings", names=tuple(ACCELERATOR_COLLECTIONS)),
    BucketSection("research", "Trajectories and research", names=("trajectories", "autoresearch_insights")),
    BucketSection("company", "Company buckets", prefixes=(_P.COMPANY_PREFIX,), admin_only=True),
    BucketSection("project", "Project buckets", prefixes=(_P.PROJECT_PREFIX, _P.SPRINT_PREFIX), admin_only=True),
    BucketSection("work_item", "Work item buckets", prefixes=(_P.WORK_ITEM_PREFIX,), admin_only=True),
    BucketSection("agent", "Agent buckets", prefixes=(_P.AGENT_PREFIX,), admin_only=True),
)

# Covered by the Redis fact listing (facts section) or deliberately not sections.
FACT_VECTOR_COLLECTIONS: Tuple[str, ...] = ("autobot_kb",)
EXCLUDED_COLLECTIONS: Tuple[str, ...] = ("semantic_query_cache", "topic_retrieval_cache")  # decision 2026-11-06


def section_for(collection: str) -> BucketSection | None:
    """The section a collection feeds, or None when it is excluded or unmapped."""
    return next((s for s in BUCKET_SECTIONS if s.matches(collection)), None)


def is_accounted_for(collection: str) -> bool:
    """True when the graph either shows the collection or has an explicit reason not to."""
    return section_for(collection) is not None or collection in FACT_VECTOR_COLLECTIONS + EXCLUDED_COLLECTIONS


def _collection_names(listed: List[Any]) -> List[str]:
    return sorted(c if isinstance(c, str) else c.name for c in listed)


def _preview(document: str | None) -> str:
    return (document or "")[:SECTION_PREVIEW_CHARS]


async def _sample_collection(client: Any, name: str, limit: int) -> Tuple[int, List[Dict[str, Any]]]:
    """Return (record count, up to ``limit`` records) of one collection."""
    collection = await client.get_collection(name)
    total = await collection.count()
    if total == 0 or limit <= 0:
        return total, []
    got = await collection.get(limit=limit, include=["documents", "metadatas"])
    ids, docs, metas = got.get("ids") or [], got.get("documents") or [], got.get("metadatas") or []
    return total, [
        {
            "id": rid,
            "preview": _preview(docs[i] if i < len(docs) else None),
            "metadata": (metas[i] if i < len(metas) else None) or {},
        }
        for i, rid in enumerate(ids)
    ]


async def build_bucket_sections(client: Any, is_admin: bool, limit: int = SECTION_SAMPLE_LIMIT) -> Dict[str, Any]:
    """Section nodes, record nodes, edges and the per-section total vs returned report."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    report: List[Dict[str, Any]] = []
    totals: Dict[str, int] = {}
    returned: Dict[str, int] = {}
    unmapped: List[str] = []
    for name in _collection_names(await client.list_collections()):
        section = section_for(name)
        if section is None:
            if not is_accounted_for(name):
                unmapped.append(name)
            continue
        if section.admin_only and not is_admin:
            continue
        try:
            total, records = await _sample_collection(client, name, limit - returned.get(section.key, 0))
        except Exception as exc:  # one broken collection must not hide the other sections
            logger.warning("Graph section %s: collection %s unreadable: %s", section.key, name, exc)
            continue
        totals[section.key] = totals.get(section.key, 0) + total
        returned[section.key] = returned.get(section.key, 0) + len(records)
        for rec in records:
            node_id = f"bucket:{name}:{rec['id']}"
            nodes.append(
                {
                    "id": node_id,
                    "name": rec["preview"] or rec["id"],
                    "type": "bucket_record",
                    "section": section.key,
                    "collection": name,
                    "metadata": rec["metadata"],
                }
            )
            edges.append({"from": f"section:{section.key}", "to": node_id, "type": "contains", "strength": 1.0})
    for section in BUCKET_SECTIONS:
        if section.key not in totals or totals[section.key] == 0:
            continue
        nodes.append(
            {
                "id": f"section:{section.key}",
                "name": section.label,
                "type": "section",
                "section": section.key,
                "metadata": {"total": totals[section.key]},
            }
        )
        report.append(section_report(section.key, section.label, totals[section.key], returned[section.key]))
    return {"nodes": nodes, "edges": edges, "sections": report, "unmapped": unmapped}


def section_report(key: str, label: str, total: int | None, returned: int) -> Dict[str, Any]:
    """Total vs returned for one section; ``limited`` is what the UI shows as a notice."""
    return {
        "key": key,
        "label": label,
        "total": total,
        "returned": returned,
        "limited": total is None or returned < total,
    }
