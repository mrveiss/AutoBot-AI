# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
RAGService's derived-content context legs, scoped to the caller (#4678, #18944).

The KB synthesis summaries and the analyzer lessons are read straight from ChromaDB collections, outside
the facts store. Each hit goes through ``filter_for_principal`` -- the one filter -- before it can join a
context, so a derived document the caller may not read never reaches a response.

Records written before the platform-docs grant existed carry no visibility metadata and would read as
private. Stored records are never rewritten here (#17038); a collection that holds platform-derived
content *by construction* supplies its grant at read time instead -- see :meth:`_visible_synthesis_docs`.
"""

from typing import Any, Dict, List, Mapping, Optional

from autobot_shared.logging_manager import get_llm_logger
from knowledge.platform_docs import PLATFORM_DOCS_GRANT
from knowledge.search_filters import KbPrincipal, filter_for_principal

logger = get_llm_logger("rag_service")

#: Metadata keys that state a record's scope. A record with none of them predates the grant.
_SCOPE_KEYS = ("visibility", "access_level", "owner_id")


def _with_legacy_grant(meta: Optional[Dict[str, Any]], grant: Optional[Mapping[str, str]]) -> Dict[str, Any]:
    """*meta*, plus *grant* only when the record states no scope at all; an explicit scope always wins."""
    meta = dict(meta or {})
    if grant and not any(k in meta for k in _SCOPE_KEYS):
        meta.update(grant)
    return meta


class RAGDerivedContextMixin:
    """Context legs mixed into ``RAGService``; relies on its ``_ownership_manager``."""

    async def _visible_docs(
        self, collection, query: str, principal: KbPrincipal, legacy_grant: Optional[Mapping[str, str]] = None
    ) -> List[str]:
        """Top documents of a derived-content *collection* that *principal* may read (#18944).

        The one filter: ``filter_for_principal`` over each hit's stored metadata. A hit with no
        ownership or visibility metadata reads as private unless the caller passes *legacy_grant*,
        which only a collection that is platform-only by construction may do.
        """
        res = await collection.query(query_texts=[query], n_results=2, include=["documents", "metadatas"])
        if not (res and res.get("ids") and res["ids"][0]):
            return []
        ids, docs = res["ids"][0], res.get("documents", [[]])[0]
        metas = list((res.get("metadatas") or [[]])[0])
        metas += [None] * (len(ids) - len(metas))
        hits = [
            {"id": i, "metadata": _with_legacy_grant(m, legacy_grant), "doc": d}
            for i, d, m in zip(ids, docs, metas)
            if d
        ]
        kept = await filter_for_principal(hits, principal, self._ownership_manager())
        return [h["doc"] for h in kept]

    async def _visible_synthesis_docs(self, collection, query: str, principal: KbPrincipal) -> List[str]:
        """``_visible_docs`` for a KB synthesis collection: grant-less legacy summaries read as platform docs.

        Platform-only by construction: ``KBSynthesizer`` is the only writer of ``kb_synthesis`` and the
        schema ``synthesis_target`` collections, and its only caller (``DocIndexerService``) feeds it
        indexed platform docs -- so a summary predating the grant was built from platform docs too.
        """
        return await self._visible_docs(collection, query, principal, legacy_grant=PLATFORM_DOCS_GRANT)

    async def _get_analyzer_lessons_context(self, query: str, principal: KbPrincipal) -> str:
        """Query the ``autobot_lessons`` ChromaDB collection for supplemental context.

        Issue #4678: Injects AnalyzerService-distilled lessons as low-weight
        supplemental context after primary synthesis summaries.  Requires
        ``RAGConfig.enable_analyzer_lessons`` to be True (checked by caller).

        Returns an empty string on any error so the main context path is never
        interrupted.

        No read-time grant here: ``autobot_lessons`` is NOT platform-only by construction --
        ``AnalyzerService.analyze_rag_session`` distils lessons from a user's query and retrieved
        results -- so a lesson stored without scope metadata stays private. Synthesis-domain lessons
        carry the grant from the write (``Lesson.to_metadata``).
        """
        try:
            from knowledge.backends import get_async_default_client

            client = await get_async_default_client()
            collection = await client.get_or_create_collection(name="autobot_lessons")
            relevant = await self._visible_docs(collection, query, principal)
            if not relevant:
                return ""
            return "Analyzer lessons:\n" + "\n".join(f"- {d}" for d in relevant)
        except Exception as exc:
            logger.debug("Analyzer lessons fetch failed (non-fatal): %s", exc)
            return ""
