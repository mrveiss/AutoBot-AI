# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
KBSynthesizer — LLM synthesis layer for KB wiki pages.

Issue #4564: Synthesizes clusters of KB docs (from DocIndexerService tiers)
into topic-summary pages stored in a ``kb_synthesis`` ChromaDB collection.
The summaries are retrieved by RAGService as optional context enrichment.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from services.knowledge.synthesis_schema_loader import CollectionConfig

logger = logging.getLogger(__name__)

_KB_SYNTHESIS_COLLECTION = "kb_synthesis"

_SYNTHESIS_PROMPT = (
    "You are a technical documentation analyst. "
    "Summarize the following AutoBot documentation pages into a single coherent "
    "topic overview. Focus on key concepts, how components interact, and actionable "
    "guidance. Return plain prose (no JSON). Maximum 400 words."
)

_MAX_DOCS_PER_CLUSTER = 10
_MAX_CHARS_PER_DOC = 2000


class KBSynthesizer:
    """Synthesize KB doc clusters into topic-summary pages in ChromaDB.

    Issue #4564: Subclass of BaseSynthesizer for KB documentation synthesis.
    Summaries are stored in the ``kb_synthesis`` ChromaDB collection and
    queried by RAGService as optional context enrichment.
    """

    COLLECTION_NAME = _KB_SYNTHESIS_COLLECTION

    def __init__(self, llm_service: Any) -> None:
        self._llm = llm_service
        self._collection: Optional[Any] = None

    # ------------------------------------------------------------------
    # BaseSynthesizer ABC interface
    # ------------------------------------------------------------------

    async def _get_collection(self) -> Any:
        """Return the kb_synthesis ChromaDB collection (lazy-init)."""
        if self._collection is None:
            from utils.chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            self._collection = await client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"description": "LLM-synthesized KB topic summaries"},
            )
        return self._collection

    async def _index_documents(self, docs: List[Any]) -> None:
        """Persist synthesized SummaryPage dicts into ChromaDB."""
        if not docs:
            return
        collection = await self._get_collection()
        ids = [d["id"] for d in docs]
        documents = [d["summary"] for d in docs]
        metadatas = [{k: v for k, v in d.items() if k not in ("id", "summary")} for d in docs]
        try:
            await collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            logger.info("KBSynthesizer: indexed %d summaries in ChromaDB", len(docs))
        except Exception:
            logger.exception("KBSynthesizer: failed to index summaries")

    async def get_relevant_context(self, topic: str, limit: int = 3) -> str:
        """Return synthesized KB summaries as a RAG context string."""
        results = await self._query_summaries(topic, limit=limit)
        if not results:
            return ""
        lines = ["KB synthesis context:"]
        for doc, meta in results:
            source = meta.get("source_paths", "")
            lines.append(f"- {doc}" + (f" [sources: {source}]" if source else ""))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def synthesize_docs(
        self,
        file_paths: List[str],
        collection_config: "Optional[CollectionConfig]" = None,
    ) -> None:
        """Synthesize indexed KB docs into topic-summary pages (best-effort).

        Called after each tier ingest in DocIndexerService.  Errors are
        logged and swallowed so ingest is never interrupted.

        Args:
            file_paths: Absolute paths to recently indexed markdown files.
            collection_config: Optional schema config whose ``prompt_template``
                overrides the generic synthesis prompt for this cluster.
        """
        if not file_paths:
            return
        try:
            await self._synthesize_cluster(file_paths, collection_config=collection_config)
        except Exception:
            logger.exception("KBSynthesizer.synthesize_docs failed (non-fatal)")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_prompt(self, collection_config: "Optional[CollectionConfig]") -> str:
        """Return the synthesis prompt for this cluster.

        Uses the collection config's ``prompt_template`` when provided;
        falls back to the generic ``_SYNTHESIS_PROMPT`` otherwise.
        """
        if collection_config is None:
            return _SYNTHESIS_PROMPT
        template = collection_config.prompt_template.strip()
        if not template:
            logger.warning(
                "KBSynthesizer: collection '%s' has empty prompt_template — using default",
                collection_config.name,
            )
            return _SYNTHESIS_PROMPT
        logger.debug(
            "KBSynthesizer: using prompt_template from collection '%s'",
            collection_config.name,
        )
        return template

    async def _synthesize_cluster(
        self,
        file_paths: List[str],
        collection_config: "Optional[CollectionConfig]" = None,
    ) -> None:
        """Build one summary page from a batch of docs."""
        docs_text = await asyncio.to_thread(self._read_docs, file_paths)
        if not docs_text.strip():
            return

        cluster_id = self._cluster_id(file_paths)
        prompt = self._resolve_prompt(collection_config)
        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": docs_text},
                ],
                temperature=0.3,
                max_tokens=600,
            )
        except Exception:
            logger.exception("KBSynthesizer: LLM call failed")
            return

        summary_text = getattr(response, "content", str(response)).strip()
        if not summary_text:
            return

        page = {
            "id": cluster_id,
            "summary": summary_text,
            "source_paths": ",".join(file_paths[:_MAX_DOCS_PER_CLUSTER]),
            "synthesized_at": time.time(),
            "doc_count": len(file_paths),
        }
        await self._index_documents([page])

    @staticmethod
    def _read_docs(file_paths: List[str]) -> str:
        """Read and concatenate doc content for LLM input (sync, run in thread)."""
        parts: List[str] = []
        for fp in file_paths[:_MAX_DOCS_PER_CLUSTER]:
            try:
                with open(fp, encoding="utf-8") as fh:
                    text = fh.read(_MAX_CHARS_PER_DOC)
                parts.append(f"## {fp}\n{text}")
            except OSError as exc:
                logger.warning("KBSynthesizer: cannot read %s: %s", fp, exc)
        return "\n\n".join(parts)

    @staticmethod
    def _cluster_id(file_paths: List[str]) -> str:
        """Stable cluster ID derived from sorted file paths."""
        key = ",".join(sorted(file_paths[:_MAX_DOCS_PER_CLUSTER]))
        return "kb_syn_" + hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:12]

    async def _query_summaries(
        self, query: str, limit: int = 3
    ) -> List[tuple[str, dict]]:
        """Query kb_synthesis collection; return list of (document, metadata)."""
        try:
            collection = await self._get_collection()
            results = await collection.query(
                query_texts=[query],
                n_results=limit,
            )
        except Exception:
            logger.exception("KBSynthesizer: query failed")
            return []

        output: List[tuple[str, dict]] = []
        if results and results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                doc = results["documents"][0][i] if results.get("documents") else ""
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                output.append((doc, meta))
        return output


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_kb_synthesizer: Optional[KBSynthesizer] = None


def get_kb_synthesizer(llm_service: Any) -> KBSynthesizer:
    """Return the singleton KBSynthesizer, creating it with llm_service if needed."""
    global _kb_synthesizer
    if _kb_synthesizer is None:
        _kb_synthesizer = KBSynthesizer(llm_service)
    return _kb_synthesizer
