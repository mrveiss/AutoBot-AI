# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge-graph sections: every ChromaDB knowledge bucket mapped to one graph section (#20945).

``BUCKET_SECTIONS`` is the single registry of which store appears in the knowledge graph. A
collection the registry neither maps nor explicitly excludes is *unmapped*; a guard test fails on
any unmapped collection that holds data, so a new bucket cannot silently stay out of the graph.
Chat conversations and query caches are not KB buckets (maintainer decision 2026-11-06).

Each section has an ``access`` kind (see ``graph_bucket_visibility``); a record is filtered by the
caller's permission FIRST, then counted and paged (``offset``, sorted by collection and id), so a
total never counts what the caller cannot read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from knowledge.backends.async_chromadb_adapter import _chroma_safe_name
from knowledge.graph_bucket_visibility import (
    OWNER,
    PUBLIC,
    TENANT_ADMIN,
    Viewer,
    collection_in_scope,
    record_page,
    visible_records,
)
from knowledge.graph_limits import GRAPH_SCAN_LIMIT, SCAN_BATCH, SECTION_PREVIEW_CHARS, SECTION_SAMPLE_LIMIT
from knowledge.index_embedding_space import (
    ACCELERATOR_COLLECTIONS,
    CODE_INDEX,
    PATTERN_INDEXES,
)
from knowledge.summary_visibility import resolve_sources
from llc.kb.collections import KbCollectionManager

logger = get_logger(__name__)


@dataclass(frozen=True)
class BucketSection:
    """One graph section: the exact collection names and name prefixes that feed it."""

    key: str
    label: str
    names: Tuple[str, ...] = ()
    prefixes: Tuple[str, ...] = ()
    access: str = OWNER  # who reads a record: PUBLIC (product docs/code), OWNER (per-user), TENANT_ADMIN

    def matches(self, collection: str) -> bool:
        """True for the logical name or the ChromaDB-stored one (``:`` is stored as ``_``, #10743)."""
        stored = _chroma_safe_name(collection)
        return (
            collection in self.names
            or stored in {_chroma_safe_name(n) for n in self.names}
            or any(collection.startswith(p + ":") or stored.startswith(p + "_") for p in self.prefixes)
        )


_P = KbCollectionManager
_MEMORY = (
    "autobot_memory",
    "autobot_lessons",
    "cognition_store",
    "knowledge_vectors",
    "knowledge_summaries",
    "platform:template_kb",
)
_RESEARCH = ("trajectories", "autoresearch_insights", "autoresearch_experiments", "security_findings")
BUCKET_SECTIONS: Tuple[BucketSection, ...] = (
    BucketSection("docs", "Documentation", names=("autobot_docs",), access=PUBLIC),
    BucketSection("memory", "Memory", names=_MEMORY),
    BucketSection(
        "code",
        "Code analysis",
        names=("autobot_code", "autobot_code_graph", CODE_INDEX, *PATTERN_INDEXES, "code_kb"),
        access=PUBLIC,
    ),
    BucketSection(
        "verbatim",
        "Verbatim and synthesis",
        names=("autobot_verbatim", "autobot_synthesis_architecture", "kb_synthesis"),
    ),
    BucketSection("embeddings", "Media embeddings", names=tuple(ACCELERATOR_COLLECTIONS)),
    BucketSection("research", "Trajectories and research", names=_RESEARCH),
    BucketSection("company", "Company buckets", prefixes=(_P.COMPANY_PREFIX,), access=TENANT_ADMIN),
    BucketSection("project", "Project buckets", prefixes=(_P.PROJECT_PREFIX, _P.SPRINT_PREFIX), access=TENANT_ADMIN),
    BucketSection("work_item", "Work item buckets", prefixes=(_P.WORK_ITEM_PREFIX,), access=TENANT_ADMIN),
    BucketSection("agent", "Agent buckets", prefixes=(_P.AGENT_PREFIX,), access=TENANT_ADMIN),
)

# Covered by the Redis fact listing (facts section) or deliberately not sections.
FACT_VECTOR_COLLECTIONS: Tuple[str, ...] = ("autobot_kb",)
EXCLUDED_COLLECTIONS: Tuple[str, ...] = ("semantic_query_cache", "topic_retrieval_cache")  # decision 2026-11-06
# Created and deleted inside one benchmark run (api/knowledge_rag.py, knowledge/rag_benchmarks.py,
# services/knowledge/autonomous_loop.py), and a Milvus collection that is not a ChromaDB bucket at all.
SCRATCH_COLLECTIONS: Tuple[str, ...] = ("benchmark_run", "real_kb_bench", "loop_eval_bench", "autobot_memories")


def section_for(collection: str) -> BucketSection | None:
    """The section a collection feeds, or None when it is excluded or unmapped."""
    return next((s for s in BUCKET_SECTIONS if s.matches(collection)), None)


def is_accounted_for(collection: str) -> bool:
    """True when the graph either shows the collection or has an explicit reason not to."""
    return (
        section_for(collection) is not None
        or collection in FACT_VECTOR_COLLECTIONS + EXCLUDED_COLLECTIONS + SCRATCH_COLLECTIONS
    )


def _collection_names(listed: List[Any]) -> List[str]:
    return sorted(c if isinstance(c, str) else c.name for c in listed)


def _preview(document: str | None) -> str:
    return (document or "")[:SECTION_PREVIEW_CHARS]


async def _scan_collection(client: Any, name: str) -> Tuple[List[Dict[str, Any]], bool]:
    """Ids and metadata of up to ``GRAPH_SCAN_LIMIT`` records of one collection, and whether it held more."""
    collection = await client.get_collection(name)
    rows: List[Dict[str, Any]] = []
    while len(rows) < GRAPH_SCAN_LIMIT:
        size = min(SCAN_BATCH, GRAPH_SCAN_LIMIT - len(rows))
        got = await collection.get(limit=size, offset=len(rows), include=["metadatas"])
        ids, metas = got.get("ids") or [], got.get("metadatas") or []
        rows.extend({"id": rid, "metadata": (metas[i] if i < len(metas) else None) or {}} for i, rid in enumerate(ids))
        if len(ids) < size:
            return rows, False
    return rows, await collection.count() > len(rows)


async def _previews(client: Any, picked: List[Tuple[str, str]]) -> Dict[Tuple[str, str], str]:
    """The preview text of each ``(collection, id)`` on the page; a failed collection read has none (id fallback)."""
    out: Dict[Tuple[str, str], str] = {}
    for name in sorted({n for n, _ in picked}):
        ids = [rid for n, rid in picked if n == name]
        try:
            got = await (await client.get_collection(name)).get(ids=ids, include=["documents"])
        except Exception as exc:  # one collection's preview must not drop the healthy sections
            logger.warning("Graph preview of collection %s unavailable: %s", name, exc)
            continue
        docs = got.get("documents") or []
        out.update(
            {(name, rid): _preview(docs[i] if i < len(docs) else None) for i, rid in enumerate(got.get("ids") or [])}
        )
    return out


SUMMARY_COLLECTION = "knowledge_summaries"


async def _readable_rows(section: BucketSection, name: str, scanned: list, viewer: Viewer, manager, kb) -> list:
    """The scanned rows the viewer may read. A summary derives from its source fact and is judged by that fact."""
    if name != SUMMARY_COLLECTION:
        return await visible_records(section.access, name, scanned, viewer, manager)
    if kb is None:
        return []  # no way to resolve the source fact: fail closed
    resolved = await resolve_sources(
        scanned, kb, lambda r: r["metadata"].get("document_id"), withhold_quarantined_source=True
    )
    by_id = {row["id"]: row for row, _ in resolved}
    judged = [{"id": row["id"], "metadata": source} for row, source in resolved]
    seen = await visible_records(section.access, name, judged, viewer, manager)
    return [by_id[r["id"]] for r in seen]


async def _section_rows(
    client: Any, section: BucketSection, names: List[str], viewer: Viewer, manager, kb: Any = None
) -> tuple:
    """Every record of the section's collections the viewer may read, sorted, and whether a scan was cut short."""
    rows: List[Tuple[str, str, Dict[str, Any]]] = []
    truncated = False
    for name in names:
        if not collection_in_scope(section.access, name, viewer):
            continue
        try:
            scanned, cut = await _scan_collection(client, name)
            seen = await _readable_rows(section, name, scanned, viewer, manager, kb)
        except Exception as exc:  # one broken collection must not hide the other sections
            logger.warning("Graph section %s: collection %s unreadable: %s", section.key, name, exc)
            continue
        truncated = truncated or cut
        rows.extend((name, r["id"], r["metadata"]) for r in seen)
    return sorted(rows, key=lambda r: (r[0], r[1])), truncated


def _nodes_of(section: BucketSection, page: List[Tuple[str, str, Dict[str, Any]]], previews: Dict) -> tuple:
    nodes, edges = [], []
    for name, rid, meta in page:
        node_id = f"bucket:{name}:{rid}"
        preview = previews.get((name, rid), "")
        nodes.append(
            {
                "id": node_id,
                "name": preview or rid,
                "type": "bucket_record",
                "section": section.key,
                "collection": name,
                "metadata": meta,
            }
        )
        edges.append({"from": f"section:{section.key}", "to": node_id, "type": "contains", "strength": 1.0})
    return nodes, edges


async def build_bucket_sections(
    client: Any,
    viewer: Viewer,
    ownership_manager: Any,
    limit: int = SECTION_SAMPLE_LIMIT,
    offset: int = 0,
    kb: Any = None,
) -> Dict[str, Any]:
    """Section nodes, record nodes, edges and the per-section visible total vs returned report.

    Permission first, then count and page: ``total`` is what the viewer may read, ``offset``/``limit``
    page that set in a stable order (collection, id).
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    report: List[Dict[str, Any]] = []
    unmapped: List[str] = []
    by_section: Dict[str, List[str]] = {}
    for name in _collection_names(await client.list_collections()):
        section = section_for(name)
        if section is None:
            if not is_accounted_for(name):
                unmapped.append(name)
            continue
        if section.access != TENANT_ADMIN or viewer.is_admin:
            by_section.setdefault(section.key, []).append(name)
    for section in (s for s in BUCKET_SECTIONS if s.key in by_section):
        rows, truncated = await _section_rows(client, section, by_section[section.key], viewer, ownership_manager, kb)
        if not rows and not truncated:
            continue
        page = rows[offset : offset + max(limit, 0)]
        record_page(viewer, section.access, page)
        previews = await _previews(client, [(n, i) for n, i, _ in page]) if page else {}
        new_nodes, new_edges = _nodes_of(section, page, previews)
        nodes.extend(new_nodes)
        edges.extend(new_edges)
        nodes.append(
            {
                "id": f"section:{section.key}",
                "name": section.label,
                "type": "section",
                "section": section.key,
                "metadata": {"total": len(rows)},
            }
        )
        report.append(section_report(section.key, section.label, len(rows), len(page), offset, truncated))
    return {"nodes": nodes, "edges": edges, "sections": report, "unmapped": unmapped}


def section_report(
    key: str, label: str, total: int | None, returned: int, offset: int = 0, truncated: bool = False
) -> Dict[str, Any]:
    """Visible total vs this page; ``limited`` is true while records remain past the page (the UI notice).

    ``truncated`` means the scan cap cut the listing short, so ``total`` is a lower bound.
    """
    unknown = total is None
    return {
        "key": key,
        "label": label,
        "total": total,
        "returned": returned,
        "limited": unknown or truncated or offset + returned < total,
        "truncated": truncated,
    }
