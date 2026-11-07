# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat citations built from knowledge-base hits (#10548).

Split out of ``api/chat.py`` (#16665) so that grandfathered module does not grow. The hits it
receives are already filtered to what the message author may read.
"""

from typing import Any, Dict, List

from api.schemas_chat import Citation
from autobot_shared.logging_manager import get_logger
from knowledge.chunk_identity import resolve_chunk_id
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge.search_filters import filter_for_user_id

logger = get_logger(__name__)


def _build_citations_from_kb_results(kb_results: List[Dict[str, Any]]) -> List[Citation]:
    """Convert raw KB search results to structured Citation objects (#10548).

    Each kb_result dict coming from search() typically carries:
      content, source (file path), score, metadata (chunk_id, title, …).
    We construct a Citation for each entry, capping at 5 to avoid payload bloat.
    """
    citations: List[Citation] = []
    for idx, result in enumerate(kb_results[:5]):
        raw_meta = result.get("metadata") or {}
        chunk_id = resolve_chunk_id({"metadata": raw_meta}) or raw_meta.get("id") or f"chunk-{idx}"
        source_path = result.get("source") or raw_meta.get("source_path") or ""
        title = raw_meta.get("title") or (source_path.split("/")[-1] if source_path else f"Source {idx + 1}")
        score = float(result.get("score") or 0.0)
        citations.append(
            Citation(id=str(chunk_id), source_type="chunk", title=title, uri=source_path or None, score=score)
        )
    return citations


async def retrieve_citations(message, knowledge_base, author_id: str | None, session_id: str) -> List[Citation]:
    """Search the KB for *message* and build citations from the hits the author may read.

    Uses the knowledge_base dependency already on the chat path (no re-retrieval). #16665: hits are
    filtered to what *author_id* may read; no author means no citations. Never raises.
    """
    if not (message.use_knowledge_base and knowledge_base):
        return []
    try:
        # Issue #13009: exclude quarantined research facts (#12622) -- this
        # citation path surfaces raw KB content directly in the response.
        kb_hits = await knowledge_base.search(query=message.content, top_k=5, filters=RESEARCH_QUARANTINE_FILTER)
        kb_hits = await filter_for_user_id(kb_hits, knowledge_base, author_id)
        citations = _build_citations_from_kb_results(kb_hits) if kb_hits else []
        if citations:
            logger.debug("[#10548] Attached %d citations to response in session %s", len(citations), session_id)
        return citations
    except Exception as _cit_err:
        logger.warning("[#10548] Citation retrieval failed (non-fatal): %s", _cit_err)
        return []
