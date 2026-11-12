# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""How and when the code graph was built (#13508), split out of ``code_indexer``.

``code_indexer`` re-exports everything here, so existing importers are unchanged.
"""

import asyncio
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from typing import Any

from autobot_shared.logging_manager import get_logger
from services.knowledge.code_index_versioning import EXTRACTOR_VERSION, grammar_versions_json

logger = get_logger(__name__)

# One provenance document per collection, at a fixed id so a run overwrites the
# previous record instead of accumulating history.
_PROVENANCE_ID = "code_graph::provenance"
_PROVENANCE_RECORD_TYPE = "graph_provenance"


@dataclass
class GraphProvenance:
    """How and when the code graph was built (#13508).

    Absence of this record means **unknown**, never fresh: a collection indexed
    before provenance existed must not read as current, which is why every
    consumer goes through ``load_graph_provenance`` returning ``None`` rather
    than a zero-valued default.

    ``nodes``/``edges``/``resolved_edges`` describe **the graph**, counted from the
    collection. ``last_run_*`` describe the run that wrote this record. Keeping
    them apart is the point: an incremental run extracts nothing, and per-run
    totals would report a healthy graph as empty.

    Every field carries a default so a record written by an older version stays
    readable — a missing field must degrade one value, not the whole record.
    """

    root_dir: str = ""
    indexed_at_commit: str = ""
    indexed_at: str = ""
    extractor_version: int = 0
    # #21316: JSON of the tree-sitter runtime + grammar versions that parsed the graph; "" = unknown.
    grammar_versions: str = ""
    files_with_extractor: int = 0
    files_total: int = 0
    nodes: int = 0
    edges: int = 0
    resolved_edges: int = 0
    unresolved_edges: int = 0
    last_run_nodes_stored: int = 0
    last_run_failures: int = 0

    @property
    def extractor_coverage(self) -> float:
        """Fraction of the code the registry recognises that this indexer can read.

        Deliberately not called "coverage": it says nothing about whether those
        files were successfully extracted on any given run, only that a grammar
        exists for them (#13510).
        """
        return self.files_with_extractor / self.files_total if self.files_total else 0.0

    @property
    def resolution_rate(self) -> float:
        """Fraction of edges in the graph that resolved to a known node."""
        return self.resolved_edges / self.edges if self.edges else 0.0

    @property
    def is_current_extractor(self) -> bool:
        """Whether the graph was built by the extractor AND the grammars this process is running (#21316)."""
        return self.extractor_version == EXTRACTOR_VERSION and self.grammar_versions == grammar_versions_json()


async def load_graph_provenance(collection: Any) -> "GraphProvenance | None":
    """Return how the graph in *collection* was built, or ``None`` if unknown.

    ``None`` covers every uncertain case — no record, an unreadable store, a
    record this build cannot parse. A collection indexed before #13508 has no
    record and therefore reads as unknown, never as fresh, which is the
    constraint the issue is explicit about.

    Async because the read is blocking store I/O; the first caller on an event
    loop would otherwise stall it.
    """
    try:
        found = await asyncio.to_thread(collection.get, ids=[_PROVENANCE_ID], include=["metadatas"])
    except Exception as exc:
        logger.warning("code_indexer: could not read graph provenance: %s", exc)
        return None
    metadatas = (found or {}).get("metadatas") or []
    if not metadatas or not isinstance(metadatas[0], dict):
        return None
    known = {f.name for f in dataclass_fields(GraphProvenance)}
    payload = {k: v for k, v in metadatas[0].items() if k in known}
    try:
        return GraphProvenance(**payload)
    except TypeError as exc:
        logger.warning("code_indexer: graph provenance record is not readable: %s", exc)
        return None
