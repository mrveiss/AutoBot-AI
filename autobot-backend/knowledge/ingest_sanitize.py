# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The prompt-injection chokepoint for knowledge-base writes (#16770).

#5064 sanitized the upload route. Every other writer -- connectors, bulk import, the OKF
adapter, the agent ``store_fact`` tool, incremental sync, background tasks and the agent
diaries -- reached ``KnowledgeBase.store_fact`` with raw text, so a document arriving by
any of those routes kept its injected instructions and later reached a prompt through
retrieval. ``store_fact`` now calls :func:`sanitize_fact_content`, which is the point:
a writer cannot skip a defence it never has to know about.

Provenance is recorded on the fact itself so retrieval can weigh trust -- which route
wrote it, whether sanitizing changed the text, and which rules matched.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger
from knowledge.query_sanitizer import sanitize_for_storage

logger = get_logger(__name__)

#: Names the writer. Taken from the caller's own ``ingest_route`` when it sets one,
#: falling back to ``source`` (which most writers already set) and then to a literal.
INJECTION_ROUTE = "ingest_route"
#: True when sanitizing actually changed the text, not merely when a rule matched:
#: LOG_ONLY rules match without rewriting, and recording those as "sanitized" would
#: overstate what was done to the fact.
INJECTION_SANITIZED = "injection_sanitized"
#: Every rule that matched, ``name:count`` pairs, comma-separated -- LOG_ONLY included,
#: so an auditor can see what was observed as well as what was rewritten. A flat string
#: because ChromaDB metadata takes scalars only (``knowledge/utils.py``).
INJECTION_RULES_HIT = "injection_rules_hit"

UNSPECIFIED_ROUTE = "unspecified"


def _route_of(metadata: Dict[str, Any]) -> str:
    """The route label to record for this write.

    ``ingest_route`` when the writer names itself. A connector already identifies itself
    in the metadata it builds, so it is labelled from that rather than made to carry a
    duplicate key; otherwise the writer's own ``source``, and failing that a literal.
    """
    explicit = metadata.get(INJECTION_ROUTE)
    if explicit:
        return str(explicit)
    if metadata.get("source_type") == "connector" and metadata.get("source_connector_id"):
        return f"connector:{metadata['source_connector_id']}"
    return str(metadata.get("source") or UNSPECIFIED_ROUTE)


def sanitize_fact_content(content: str, metadata: Dict[str, Any] | None) -> Tuple[str, Dict[str, Any]]:
    """Neutralise injection payloads in *content*; stamp provenance on *metadata*.

    Returns the text to store and the metadata to store with it.

    Sanitizing here is idempotent: ``query_sanitizer`` never re-wraps a span an earlier
    pass already escaped, so the call sites that sanitize their own text first -- the
    upload route, the link pipeline, the doc indexer -- are not double-stripped.
    """
    metadata = metadata if metadata is not None else {}
    route = _route_of(metadata)
    result = sanitize_for_storage(content, source=route)
    metadata[INJECTION_ROUTE] = route
    metadata[INJECTION_SANITIZED] = result.sanitized_text != content
    metadata[INJECTION_RULES_HIT] = ",".join(f"{rule}:{count}" for rule, count in sorted(result.hits.items()))
    if result.hits:
        logger.warning("Injection patterns in a stored fact: route=%s hits=%s", route, result.hits)
    return result.sanitized_text, metadata
