# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Board decision log writer (GH#8243).

Indexes each resolved board approval into the company decisions KB collection
so future decisions can be informed by past rationale via RAG queries.

Decision collection naming: ``company:{company_id}:decisions``
Collection is write-once per approval — ``DecisionLogWriter`` is the sole writer.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_COMPANY_PREFIX = "company"
_DECISIONS_SUFFIX = "decisions"


def _decisions_collection(company_id: uuid.UUID | str) -> str:
    """Return the canonical collection name for company decisions.

    Format: ``company:{company_id}:decisions``
    Consistent with KbCollectionManager naming (GH#8235).
    """
    cid = str(company_id) if isinstance(company_id, uuid.UUID) else company_id
    return f"{_COMPANY_PREFIX}:{cid}:{_DECISIONS_SUFFIX}"


def _compose_document(approval: Any) -> str:
    """Build a human-readable decision document for KB indexing."""
    payload_summary = json.dumps(approval.payload or {}, ensure_ascii=False)
    decided_at = approval.decided_at.isoformat() if approval.decided_at else "unknown"
    decision_note = (approval.payload or {}).get("decision_note", "")
    lines = [
        f"Type: {approval.type}",
        f"Decision: {approval.status}",
        f"Requested by: {approval.requested_by_agent_id}",
        f"Decided at: {decided_at}",
    ]
    if decision_note:
        lines.append(f"Rationale: {decision_note}")
    lines.append(f"Payload summary: {payload_summary}")
    return "\n".join(lines)


class DecisionLogWriter:
    """Writes resolved board approval decisions to the company decisions KB.

    The collection ``company:{company_id}:decisions`` is read-only after write —
    this class is the only writer.  All other code that touches decisions must
    use ``DecisionLogReader`` or the search/list API endpoints.
    """

    async def write(self, approval: Any) -> None:
        """Index a resolved approval into the company decisions KB.

        Args:
            approval: LLCApproval ORM instance with status APPROVED or REJECTED.

        Raises:
            ValueError: If approval is still pending.
            RuntimeError: If KB write fails.
        """
        from ..models.enums import ApprovalStatus

        if approval.status == ApprovalStatus.PENDING.value:
            raise ValueError(f"Approval {approval.id} is still pending; cannot log undecided approval")

        company_id = str(approval.company_id)
        collection_name = _decisions_collection(company_id)
        doc_text = _compose_document(approval)
        doc_id = f"decision:{approval.id}"

        metadata: Dict[str, Any] = {
            "approval_type": approval.type,
            "decision": approval.status,
            "decided_at": approval.decided_at.isoformat() if approval.decided_at else "",
            "company_id": company_id,
            "approval_id": str(approval.id),
        }

        try:
            from knowledge import get_knowledge_base  # lazy — avoids chromadb at import time

            kb = await get_knowledge_base()
            collection = await kb._async_chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"entity_type": "company", "entity_id": company_id},
            )
            # Upsert so re-runs are idempotent
            existing = await collection.get(ids=[doc_id])
            if existing and existing.get("ids"):
                logger.info("Decision already indexed — skipping: approval_id=%s", approval.id)
                return

            await collection.add(
                ids=[doc_id],
                documents=[doc_text],
                metadatas=[metadata],
            )
            logger.info(
                "Decision indexed: approval_id=%s company=%s type=%s decision=%s",
                approval.id,
                company_id,
                approval.type,
                approval.status,
            )
        except Exception as exc:
            logger.error(
                "Failed to index decision approval_id=%s: %s",
                approval.id,
                exc,
            )
            raise RuntimeError(f"Failed to index decision for approval {approval.id}") from exc


class DecisionLogReader:
    """Read-only access to the company decisions KB collection."""

    async def search(
        self,
        company_id: uuid.UUID | str,
        query: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """RAG search over the decision collection.

        Args:
            company_id: Company to scope the search.
            query: Free-text query string.
            n_results: Maximum number of results.

        Returns:
            List of result dicts with ``text``, ``metadata``, and ``distance``.
        """
        collection_name = _decisions_collection(company_id)
        try:
            from knowledge import get_knowledge_base  # lazy — avoids chromadb at import time

            kb = await get_knowledge_base()
            try:
                collection = await kb._async_chroma_client.get_collection(collection_name)
            except Exception:
                logger.debug("Decisions collection does not exist for company %s", company_id)
                return []

            results = await collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )
            return _format_query_results(results)
        except Exception as exc:
            logger.error("Decision search failed for company %s: %s", company_id, exc)
            return []

    async def list_decisions(
        self,
        company_id: uuid.UUID | str,
        approval_type: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List decisions with optional type and date filters.

        Args:
            company_id: Company scope.
            approval_type: Optional filter by approval type string.
            since: Optional lower bound on ``decided_at``.
            until: Optional upper bound on ``decided_at``.
            limit: Page size.
            offset: Page offset.

        Returns:
            List of decision metadata dicts.
        """
        collection_name = _decisions_collection(company_id)
        try:
            from knowledge import get_knowledge_base  # lazy — avoids chromadb at import time

            kb = await get_knowledge_base()
            try:
                collection = await kb._async_chroma_client.get_collection(collection_name)
            except Exception:
                logger.debug("Decisions collection does not exist for company %s", company_id)
                return []

            # Fetch all records and filter in-process (ChromaDB metadata range queries
            # require a local filter step for date comparisons).
            raw = await collection.get(include=["metadatas", "documents"])
            items = _zip_get_results(raw)

            if approval_type:
                items = [i for i in items if i.get("approval_type") == approval_type]

            if since:
                since_str = since.isoformat()
                items = [i for i in items if i.get("decided_at", "") >= since_str]

            if until:
                until_str = until.isoformat()
                items = [i for i in items if i.get("decided_at", "") <= until_str]

            # Sort newest-first by decided_at
            items.sort(key=lambda x: x.get("decided_at", ""), reverse=True)
            return items[offset : offset + limit]

        except Exception as exc:
            logger.error("Decision list failed for company %s: %s", company_id, exc)
            return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_query_results(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]
    out = []
    for i, doc_id in enumerate(ids):
        out.append(
            {
                "id": doc_id,
                "text": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "distance": dists[i] if i < len(dists) else None,
            }
        )
    return out


def _zip_get_results(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = raw.get("ids") or []
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or []
    out = []
    for i, doc_id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        out.append({**meta, "id": doc_id, "text": docs[i] if i < len(docs) else ""})
    return out


__all__ = ["DecisionLogWriter", "DecisionLogReader"]
