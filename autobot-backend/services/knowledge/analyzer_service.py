# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AnalyzerService — LLM-reasoned lesson distillation after synthesis/RAG runs.

Issue #4678: After a synthesis run, complex workflow, or RAG retrieval session,
AutoBot previously discarded all qualitative context about what worked.  This
service closes that gap: it asks the LLM "what patterns should be reused?" and
writes the resulting lessons into a ``autobot_lessons`` ChromaDB collection so
future RAGService calls can inject them as lightweight supplemental context.

Trigger points
--------------
1. After ``KBSynthesizer.synthesize_docs()`` — analyze output quality vs. input docs.
2. After ``RetrievalLearner.record_pattern_outcome()`` on strong positive outcomes.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_LESSONS_COLLECTION = "autobot_lessons"

_SYNTHESIS_ANALYSIS_PROMPT = (
    "You are an expert knowledge engineer reviewing a synthesis run. "
    "Given the input documents and the synthesized output, identify: "
    "1. What patterns or content clusters led to a high-quality summary? "
    "2. What should be done differently next time to improve the output? "
    "Return 1–3 concise, actionable lessons as plain prose sentences (one per line). "
    "Do NOT use JSON, bullet markers, or numbering."
)

_RAG_ANALYSIS_PROMPT = (
    "You are an expert retrieval engineer reviewing a RAG session. "
    "Given the query, the retrieved results, and optional user feedback, identify: "
    "1. What retrieval patterns led to relevant results? "
    "2. What should be adjusted (reranking, query reformulation, source selection) next time? "
    "Return 1–3 concise, actionable lessons as plain prose sentences (one per line). "
    "Do NOT use JSON, bullet markers, or numbering."
)

# Score threshold above which a synthesis/retrieval run is considered notable.
_MIN_SCORE_DELTA = 0.1
# Maximum characters of a single source doc to include in the analysis prompt.
_MAX_SOURCE_CHARS = 1500
# Maximum number of source docs to include in the prompt.
_MAX_SOURCE_DOCS = 5


@dataclass
class Lesson:
    """A distilled, actionable lesson extracted from a knowledge operation."""

    content: str
    domain: str  # "synthesis" | "retrieval" | "workflow"
    score_delta: float  # improvement magnitude that triggered this lesson
    tags: List[str] = field(default_factory=list)
    run_id: str = ""

    def lesson_id(self) -> str:
        """Stable ID derived from content hash (for ChromaDB upsert deduplication)."""
        key = f"{self.domain}:{self.content}"
        return "lesson_" + hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:12]

    def to_metadata(self) -> dict:
        """Flat string metadata dict suitable for ChromaDB."""
        return {
            "domain": self.domain,
            "score_delta": str(self.score_delta),
            "tags": ",".join(self.tags),
            "run_id": self.run_id,
            "created_at": str(time.time()),
        }


class AnalyzerService:
    """Distil LLM-reasoned lessons from synthesis and RAG outcomes.

    Issue #4678: Analogous to the Analyzer agent in ASI-Evolve — takes
    operation output and asks the LLM what patterns should be reused, then
    persists those lessons in ChromaDB for future context injection.
    """

    COLLECTION_NAME = _LESSONS_COLLECTION

    def __init__(self, llm_service: Any) -> None:
        self._llm = llm_service
        self._collection: Any | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_synthesis_run(
        self,
        run_id: str,
        input_docs: List[str],
        output_summary: str,
        score: float,
    ) -> List[Lesson]:
        """Ask the LLM to distil lessons from a synthesis run.

        Only runs when ``score`` (a quality signal, e.g. length-normalised
        output length ratio) exceeds ``_MIN_SCORE_DELTA`` so trivial runs
        are skipped.

        Args:
            run_id: Unique identifier for the synthesis run (e.g. cluster_id).
            input_docs: Raw text of the source documents fed to the synthesizer.
            output_summary: Text produced by the synthesizer.
            score: Quality signal (0–1); skipped when below _MIN_SCORE_DELTA.

        Returns:
            List of Lesson objects; empty list on LLM failure or low score.
        """
        if score < _MIN_SCORE_DELTA:
            logger.debug(
                "AnalyzerService: skipping synthesis run %s — score %.3f below threshold",
                run_id,
                score,
            )
            return []

        truncated_docs = self._truncate_docs(input_docs)
        user_content = f"=== Input documents ===\n{truncated_docs}\n\n" f"=== Synthesized output ===\n{output_summary}"
        messages = [
            {"role": "system", "content": _SYNTHESIS_ANALYSIS_PROMPT},
            {"role": "user", "content": user_content},
        ]
        raw = await self._call_llm(messages)
        if not raw:
            return []

        lessons = self._parse_lessons(raw, domain="synthesis", score_delta=score, run_id=run_id)
        logger.info(
            "AnalyzerService: distilled %d lesson(s) from synthesis run %s",
            len(lessons),
            run_id,
        )
        return lessons

    async def analyze_rag_session(
        self,
        query: str,
        results: List[Any],
        user_feedback: str | None = None,
    ) -> List[Lesson]:
        """Ask the LLM to distil lessons from a RAG retrieval session.

        Args:
            query: The original search query.
            results: Search result objects (uses ``content`` attribute when present).
            user_feedback: Optional free-text feedback from the user.

        Returns:
            List of Lesson objects; empty on LLM failure or empty results.
        """
        if not results:
            return []

        results_text = self._format_results(results)
        feedback_section = f"\n\n=== User feedback ===\n{user_feedback}" if user_feedback else ""
        user_content = f"=== Query ===\n{query}\n\n" f"=== Retrieved results ===\n{results_text}" f"{feedback_section}"
        messages = [
            {"role": "system", "content": _RAG_ANALYSIS_PROMPT},
            {"role": "user", "content": user_content},
        ]
        raw = await self._call_llm(messages)
        if not raw:
            return []

        # Use a neutral score_delta for RAG sessions (no explicit quality signal).
        score_delta = 0.5 if user_feedback else 0.2
        lessons = self._parse_lessons(
            raw,
            domain="retrieval",
            score_delta=score_delta,
            run_id=f"rag:{hashlib.md5(query.encode(), usedforsecurity=False).hexdigest()[:8]}",
        )
        logger.info(
            "AnalyzerService: distilled %d lesson(s) from RAG session (query='%s...')",
            len(lessons),
            query[:50],
        )
        return lessons

    async def store_lessons(
        self,
        lessons: List[Lesson],
        collection: str = _LESSONS_COLLECTION,
    ) -> None:
        """Persist lessons to a ChromaDB collection (best-effort).

        Args:
            lessons: Lessons to store.
            collection: Target ChromaDB collection name.
        """
        if not lessons:
            return
        try:
            col = await self._get_collection(collection)
            ids = [lsn.lesson_id() for lsn in lessons]
            documents = [lsn.content for lsn in lessons]
            metadatas = [lsn.to_metadata() for lsn in lessons]
            await col.upsert(ids=ids, documents=documents, metadatas=metadatas)
            logger.info(
                "AnalyzerService: stored %d lesson(s) in collection '%s'",
                len(lessons),
                collection,
            )
        except Exception:
            logger.exception("AnalyzerService: failed to store lessons (non-fatal)")

    async def get_lessons_context(self, query: str, limit: int = 3) -> str:
        """Query the lessons collection and return a context string.

        Used by RAGService to inject low-weight supplemental context.

        Args:
            query: Query text to retrieve relevant lessons.
            limit: Maximum number of lessons to return.

        Returns:
            Non-empty context string when lessons are found; empty string otherwise.
        """
        try:
            col = await self._get_collection()
            results = await col.query(query_texts=[query], n_results=limit)
        except Exception:
            logger.debug("AnalyzerService: lessons query failed (non-fatal)")
            return ""

        if not (results and results.get("ids") and results["ids"][0]):
            return ""

        docs = results.get("documents", [[]])[0]
        relevant = [d for d in docs if d]
        if not relevant:
            return ""

        lines = ["Analyzer lessons:"] + [f"- {d}" for d in relevant]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_collection(self, name: str | None = None) -> Any:
        """Return a ChromaDB collection (lazy-init, cached for default name)."""
        target = name or self.COLLECTION_NAME
        if name is None:
            if self._collection is None:
                from knowledge.backends import get_async_default_client

                client = await get_async_default_client()
                self._collection = await client.get_or_create_collection(
                    name=target,
                    metadata={"description": "Analyzer-distilled lessons for context injection"},
                )
            return self._collection

        from knowledge.backends import get_async_default_client

        client = await get_async_default_client()
        return await client.get_or_create_collection(
            name=target,
            metadata={"description": "Analyzer-distilled lessons for context injection"},
        )

    async def _call_llm(self, messages: List[dict]) -> str:
        """Call the LLM service and return stripped text content.

        Returns empty string on any failure (graceful no-op).
        """
        try:
            response = await self._llm.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=400,
            )
            return getattr(response, "content", str(response)).strip()
        except Exception:
            logger.exception("AnalyzerService: LLM call failed (non-fatal)")
            return ""

    @staticmethod
    def _parse_lessons(
        raw_text: str,
        domain: str,
        score_delta: float,
        run_id: str,
    ) -> List[Lesson]:
        """Split LLM output into individual Lesson objects (one per non-empty line)."""
        lessons: List[Lesson] = []
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            lessons.append(
                Lesson(
                    content=line,
                    domain=domain,
                    score_delta=score_delta,
                    tags=[domain],
                    run_id=run_id,
                )
            )
        return lessons

    @staticmethod
    def _truncate_docs(docs: List[str]) -> str:
        """Truncate and join source docs for inclusion in analysis prompt."""
        parts: List[str] = []
        for i, doc in enumerate(docs[:_MAX_SOURCE_DOCS]):
            parts.append(f"[Doc {i + 1}]\n{doc[:_MAX_SOURCE_CHARS]}")
        return "\n\n".join(parts)

    @staticmethod
    def _format_results(results: List[Any]) -> str:
        """Format RAG search results for inclusion in analysis prompt."""
        lines: List[str] = []
        for i, r in enumerate(results[:_MAX_SOURCE_DOCS], 1):
            content = getattr(r, "content", str(r))
            lines.append(f"[Result {i}] {content[:_MAX_SOURCE_CHARS]}")
        return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_analyzer_service: AnalyzerService | None = None


def get_analyzer_service(llm_service: Any) -> AnalyzerService:
    """Return the singleton AnalyzerService, creating it with llm_service if needed."""
    global _analyzer_service
    if _analyzer_service is None:
        _analyzer_service = AnalyzerService(llm_service)
    return _analyzer_service
