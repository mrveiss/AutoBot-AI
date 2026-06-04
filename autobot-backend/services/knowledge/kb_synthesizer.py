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
import time
from typing import TYPE_CHECKING, Any, List

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    from services.knowledge.synthesis_schema_loader import CollectionConfig

logger = get_logger(__name__)

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
    Summaries are stored in ChromaDB collections (default: ``kb_synthesis``,
    or the per-collection ``synthesis_target`` from synthesis_schema.yaml) and
    queried by RAGService as optional context enrichment.

    Issue #4678: After each successful synthesis the AnalyzerService is called
    to distil lessons into ``autobot_lessons`` for future context injection.
    """

    COLLECTION_NAME = _KB_SYNTHESIS_COLLECTION

    def __init__(
        self,
        llm_service: Any,
        provenance_log: "Any | None" = None,
    ) -> None:
        self._llm = llm_service
        self._collection: Any | None = None
        # Cache of named collections keyed by collection name.
        self._named_collections: dict[str, Any] = {}
        # Issue #4678: lazy-init AnalyzerService (same LLM service).
        self._analyzer: Any | None = None
        # Issue #4681: track last run_id per collection for parent→child chain.
        self._last_run_id: dict[str, str] = {}
        # Lazy import to avoid circular deps at module load time.
        if provenance_log is None:
            from services.knowledge.synthesis_provenance import SynthesisProvenanceLog

            provenance_log = SynthesisProvenanceLog()
        self._provenance_log = provenance_log

    # ------------------------------------------------------------------
    # BaseSynthesizer ABC interface
    # ------------------------------------------------------------------

    async def _get_collection(self, collection_name: str | None = None) -> Any:
        """Return a ChromaDB collection (lazy-init).

        Args:
            collection_name: Override the collection name.  When None, the
                default ``_KB_SYNTHESIS_COLLECTION`` is used and the result is
                cached on ``self._collection`` for backward compatibility.
        """
        name = collection_name or self.COLLECTION_NAME
        if collection_name is None:
            if self._collection is None:
                from knowledge.backends import get_async_default_client

                client = await get_async_default_client()
                self._collection = await client.get_or_create_collection(
                    name=name,
                    metadata={"description": "LLM-synthesized KB topic summaries"},
                )
            return self._collection

        if name not in self._named_collections:
            from knowledge.backends import get_async_default_client

            client = await get_async_default_client()
            self._named_collections[name] = await client.get_or_create_collection(
                name=name,
                metadata={"description": "LLM-synthesized KB topic summaries"},
            )
        return self._named_collections[name]

    async def _index_documents(self, docs: List[Any], collection_name: str | None = None) -> None:
        """Persist synthesized SummaryPage dicts into ChromaDB.

        Args:
            docs: List of summary page dicts with at least ``id`` and ``summary``.
            collection_name: Target collection name override; None uses the default.
        """
        if not docs:
            return
        collection = await self._get_collection(collection_name)
        ids = [d["id"] for d in docs]
        documents = [d["summary"] for d in docs]
        metadatas = [{k: v for k, v in d.items() if k not in ("id", "summary")} for d in docs]
        try:
            await collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            logger.info(
                "KBSynthesizer: indexed %d summaries in ChromaDB collection '%s'",
                len(docs),
                collection_name or self.COLLECTION_NAME,
            )
        except Exception:
            logger.exception("KBSynthesizer: failed to index summaries")

    async def get_relevant_context(
        self,
        topic: str,
        limit: int = 3,
        collection_names: List[str] | None = None,
    ) -> str:
        """Return synthesized KB summaries as a RAG context string.

        Queries the default ``kb_synthesis`` collection plus any additional
        names provided via ``collection_names`` (e.g. from synthesis_schema).

        Args:
            topic: Query text.
            limit: Maximum results per collection.
            collection_names: Extra collection names to query in addition to
                the default.  Duplicates are skipped.
        """
        all_names: List[str | None] = [None]  # None → default collection
        seen = {self.COLLECTION_NAME}
        for name in collection_names or []:
            if name and name not in seen:
                all_names.append(name)
                seen.add(name)

        lines = ["KB synthesis context:"]
        found_any = False
        for col_name in all_names:
            results = await self._query_summaries(topic, limit=limit, collection_name=col_name)
            for doc, meta in results:
                found_any = True
                source = meta.get("source_paths", "")
                lines.append(f"- {doc}" + (f" [sources: {source}]" if source else ""))
        return "\n".join(lines) if found_any else ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def synthesize_docs(
        self,
        file_paths: List[str],
        collection_config: "CollectionConfig | None" = None,
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

    # ------------------------------------------------------------------
    # Issue #4675: prompt evolution helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_synthesis_output(text: str) -> float:
        """Score a synthesis output on [0.0, 1.0].

        Combines a token-count score (rewards 50–2000 words) with a
        uniqueness score (penalises repetitive sentences).

        Issue #4675.
        """
        words = text.split()
        word_count = len(words)
        if word_count == 0:
            return 0.0

        # Token-count score — linear decay outside [50, 2000].
        if 50 <= word_count <= 2000:
            token_score = 1.0
        elif word_count < 50:
            token_score = word_count / 50.0
        else:
            token_score = max(0.0, 1.0 - (word_count - 2000) / 2000.0)

        # Uniqueness score — unique sentences / total sentences.
        sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        total = len(sentences)
        if total == 0:
            uniqueness_score = 1.0
        else:
            uniqueness_score = len(set(sentences)) / total

        return min(1.0, token_score * 0.6 + uniqueness_score * 0.4)

    async def _select_prompt_variant(
        self,
        collection_name: str,
        variants: list,
        fallback: str,
    ) -> tuple:
        """Select a prompt variant via UCB1 bandit strategy.

        Reads recent provenance entries for ``collection_name`` and applies
        UCB1 to balance exploration vs. exploitation across ``variants``.

        Args:
            collection_name: Collection key used for provenance lookup.
            variants: List of alternate prompt strings from CollectionConfig.
            fallback: Base prompt text used when no variants are defined.

        Returns:
            Tuple of (prompt_text, variant_id) where variant_id is one of
            "base", "variant_0", "variant_1", …

        Issue #4675.
        """
        if not variants:
            return (fallback, "base")

        # Build variant map: id → text
        all_variants = {"base": fallback}
        for i, v in enumerate(variants):
            all_variants[f"variant_{i}"] = v

        # Read recent runs for this collection.
        try:
            entries = await self._provenance_log.get_recent(limit=10)
        except Exception:
            logger.debug("_select_prompt_variant: provenance read failed, defaulting to base")
            return (fallback, "base")

        # Accumulate (n_pulls, total_score) per variant.
        import math

        stats: dict = {vid: [0, 0.0] for vid in all_variants}
        for entry in entries:
            if entry.get("prompt_template") != collection_name and entry.get("collection_name") != collection_name:
                continue
            vid = str(entry.get("prompt_variant", "base"))
            if vid not in stats:
                continue
            stats[vid][0] += 1
            stats[vid][1] += float(entry.get("score", 0.0))

        total_runs = sum(s[0] for s in stats.values())

        # Cold-start: pick first untried variant.
        for vid in all_variants:
            if stats[vid][0] == 0:
                logger.debug(
                    "_select_prompt_variant: cold-start exploration → %s for '%s'",
                    vid,
                    collection_name,
                )
                return (all_variants[vid], vid)

        # UCB1 selection.
        log_total = math.log(max(total_runs, 1))
        best_vid = max(
            all_variants,
            key=lambda v: (stats[v][1] / stats[v][0]) + math.sqrt(2 * log_total / stats[v][0]),
        )
        logger.debug(
            "_select_prompt_variant: UCB1 selected %s for '%s'",
            best_vid,
            collection_name,
        )
        return (all_variants[best_vid], best_vid)

    def _resolve_prompt(self, collection_config: "CollectionConfig | None") -> str:
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
        collection_config: "CollectionConfig | None" = None,
    ) -> None:
        """Build one summary page from a batch of docs.

        Writes the result to the collection named by
        ``collection_config.synthesis_target`` when that field is non-empty;
        otherwise falls back to the default ``kb_synthesis`` collection.
        """
        docs_text = await asyncio.to_thread(self._read_docs, file_paths)
        if not docs_text.strip():
            return

        cluster_id = self._cluster_id(file_paths)
        # Issue #4675: UCB1 variant selection.
        base_prompt = self._resolve_prompt(collection_config)
        variants = collection_config.prompt_variants if collection_config is not None else []
        collection_key_for_ucb = collection_config.name if collection_config is not None else "default"
        prompt, variant_id = await self._select_prompt_variant(collection_key_for_ucb, variants, base_prompt)
        if "{documents}" in prompt:
            messages = [{"role": "user", "content": prompt.format(documents=docs_text)}]
        else:
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": docs_text},
            ]
        override_model: str | None = collection_config.synthesis_model if collection_config is not None else None
        chat_kwargs: dict = {"messages": messages, "temperature": 0.3, "max_tokens": 600}
        if override_model:
            chat_kwargs["model"] = override_model
            logger.debug(
                "KBSynthesizer: using synthesis_model override '%s' for collection '%s'",
                override_model,
                collection_config.name if collection_config else "<default>",  # type: ignore[union-attr]
            )
        try:
            response = await self._llm.chat(**chat_kwargs)
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
        target_collection: str | None = None
        if collection_config is not None:
            target = collection_config.synthesis_target.strip()
            if target:
                target_collection = target
                logger.debug(
                    "KBSynthesizer: writing cluster to synthesis_target '%s'",
                    target_collection,
                )
        start = time.monotonic()
        await self._index_documents([page], collection_name=target_collection)
        duration_ms = int((time.monotonic() - start) * 1000)

        collection_key = target_collection or self.COLLECTION_NAME
        prompt_name = collection_config.name if collection_config is not None else "default"
        # Issue #4681: link this run to its predecessor for lineage chain.
        parent_run_id: str | None = self._last_run_id.get(collection_key)
        await self._provenance_log.log_run(
            run_id=cluster_id,
            source_docs=file_paths[:_MAX_DOCS_PER_CLUSTER],
            synthesis_ids=[cluster_id],
            llm_model=getattr(self._llm, "model", "unknown"),
            prompt_template=prompt_name,
            duration_ms=duration_ms,
            parent_run_id=parent_run_id,
            source_doc_ids=file_paths[:_MAX_DOCS_PER_CLUSTER],
            prompt_variant=variant_id,
            score=self._score_synthesis_output(summary_text),
            collection_name=collection_key,
        )
        # Advance lineage pointer for this collection.
        self._last_run_id[collection_key] = cluster_id

        # Issue #4678: distil lessons from this synthesis run (best-effort).
        await self._run_analyzer(
            run_id=cluster_id,
            input_docs=docs_text,
            output_summary=summary_text,
        )

    async def _run_analyzer(self, run_id: str, input_docs: str, output_summary: str) -> None:
        """Invoke AnalyzerService post-synthesis; errors are logged and swallowed.

        Issue #4678.
        """
        try:
            from services.knowledge.analyzer_service import get_analyzer_service

            if self._analyzer is None:
                self._analyzer = get_analyzer_service(self._llm)
            score = min(len(output_summary) / max(len(input_docs), 1), 1.0)
            lessons = await self._analyzer.analyze_synthesis_run(
                run_id=run_id,
                input_docs=[input_docs],
                output_summary=output_summary,
                score=score,
            )
            if lessons:
                await self._analyzer.store_lessons(lessons)
        except Exception:
            logger.debug("_run_analyzer: best-effort call failed, skipping", exc_info=True)

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
        self, query: str, limit: int = 3, collection_name: str | None = None
    ) -> List[tuple[str, dict]]:
        """Query a synthesis collection; return list of (document, metadata).

        Args:
            query: Query text.
            limit: Maximum results.
            collection_name: Collection to query.  None uses the default.
        """
        try:
            collection = await self._get_collection(collection_name)
            results = await collection.query(
                query_texts=[query],
                n_results=limit,
            )
        except Exception:
            logger.debug(
                "KBSynthesizer: query failed for collection '%s' (non-fatal)",
                collection_name or self.COLLECTION_NAME,
            )
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

_kb_synthesizer: KBSynthesizer | None = None


def get_kb_synthesizer(llm_service: Any) -> KBSynthesizer:
    """Return the singleton KBSynthesizer, creating it with llm_service if needed."""
    global _kb_synthesizer
    if _kb_synthesizer is None:
        _kb_synthesizer = KBSynthesizer(llm_service)
    return _kb_synthesizer
