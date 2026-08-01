# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sprint KB summarizer — LLM-summarize and merge into project KB on close (GH#8238).

On sprint close:
  1. Fetch all documents from ``sprint:{sprint_id}`` ChromaDB collection.
  2. ≤ 10 docs  → merge directly into ``project:{project_id}`` (no LLM call).
  3. > 10 docs  → LLM-summarize then index the summary into ``project:{project_id}``.
  4. Store the summary text on the sprint row (``kb_summary`` column).
  5. Archive the sprint collection via KbCollectionManager.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from llm_shared.types import LLMType

from ..kb.collections import KbCollectionManager
from ..models.sprint import LLCSprint

if TYPE_CHECKING:
    # Deferred to avoid a circular import: llc.services.__init__ imports
    # sprint_autoclose, which imports this module — a module-level import
    # here of anything under ``llc.services`` would try to re-enter this
    # partially-initialized module. Actual runtime use is via lazy imports
    # inside the functions below (GH#12619).
    from ..services.agent_scorecard import AgentScore, SprintScorecard

logger = get_logger(__name__)

_SUMMARIZE_THRESHOLD = 10
_MAX_PROMPT_CHARS = 32_768  # ≈8192 tokens at 4 chars/token; caps combined input before LLM

_SUMMARIZE_PROMPT = (
    "You are summarizing a software sprint knowledge base for long-term archival.\n"
    "Below are the raw sprint artifacts separated by '---'.\n"
    "Summarize them into four concise sections:\n"
    "1. Accomplishments\n"
    "2. Key Decisions\n"
    "3. Learnings\n"
    "4. Unresolved Items\n"
    "Be concise. Use bullet points per section. Do not repeat obvious facts.\n\n"
    "{documents}"
)


class SprintKbSummarizer:
    """Summarizes a closed sprint's KB into the project KB.

    Accepts an optional ``AsyncSession``; if provided, the sprint row is
    updated with the generated summary text (``kb_summary`` column).
    The session is NOT committed here — the caller is responsible.
    """

    def __init__(
        self,
        kb_collection_manager: Optional[KbCollectionManager] = None,
    ) -> None:
        self._km = kb_collection_manager or KbCollectionManager()

    async def summarize_and_merge(
        self,
        sprint_id: uuid.UUID,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Optional[str]:
        """Summarize sprint KB and merge into project KB.

        Args:
            sprint_id: UUID of the sprint that just closed.
            session: Optional SQLAlchemy session to persist summary text on sprint row.

        Returns:
            Summary text if LLM summarization occurred, else None.
        """
        sprint_collection = KbCollectionManager.collection_name(KbCollectionManager.SPRINT_PREFIX, sprint_id)

        if session is None:
            logger.warning(
                "summarize_and_merge called without session for sprint %s; "
                "cannot resolve project_id — merge skipped, archive only",
                sprint_id,
            )
            try:
                await self._km.archive_collection(KbCollectionManager.SPRINT_PREFIX, sprint_id)
            except Exception:
                logger.error("Failed to archive collection for sprint %s", sprint_id)
                raise
            return None

        sprint, project_id = await self._load_sprint_context(sprint_id, session)

        if project_id is None:
            logger.warning(
                "Sprint %s has no parent project in DB; skipping KB merge",
                sprint_id,
            )
            try:
                await self._km.archive_collection(KbCollectionManager.SPRINT_PREFIX, sprint_id)
            except Exception:
                logger.error("Failed to archive collection for sprint %s", sprint_id)
                raise
            return None

        project_collection = KbCollectionManager.collection_name(KbCollectionManager.PROJECT_PREFIX, project_id)

        docs = await self._fetch_documents(sprint_collection)
        doc_count = len(docs)

        summary_text: Optional[str] = None

        try:
            if doc_count == 0:
                logger.info("Sprint %s KB collection is empty; nothing to merge", sprint_id)
            elif doc_count <= _SUMMARIZE_THRESHOLD:
                await self._direct_merge(docs, project_collection, sprint_id, project_id)
                summary_text = f"[direct-merged: {doc_count} docs]"
            else:
                summary_text = await self._llm_summarize_and_index(
                    docs, project_collection, sprint_id, project_id, sprint=sprint
                )
        except Exception:
            logger.error(
                "Write to project KB failed for sprint %s",
                sprint_id,
            )
            raise
        finally:
            await self._km.archive_collection(KbCollectionManager.SPRINT_PREFIX, sprint_id)

        scorecard_section = await self._build_agent_scorecard_section(sprint_id, session)
        final_summary = self._combine_summary(summary_text, scorecard_section)

        if final_summary and session is not None and sprint is not None:
            sprint.kb_summary = final_summary  # type: ignore[attr-defined]
            await session.flush()

        return summary_text

    # ------------------------------------------------------------------
    # Agent scorecard (GH#12619)
    # ------------------------------------------------------------------

    async def _build_agent_scorecard_section(
        self,
        sprint_id: uuid.UUID,
        session: Optional[AsyncSession],
    ) -> Optional[str]:
        """Build the rendered per-agent scorecard section, or None if unavailable.

        Best-effort: a scorecard aggregation failure must never block sprint
        close / KB merge, so any error is logged and swallowed here.
        """
        if session is None:
            return None
        # Lazy import — see the module-level TYPE_CHECKING note above.
        from ..services.agent_scorecard import AgentScorecardService
        from ..services.sprint_planning import SprintNotFound

        try:
            scorecard = await AgentScorecardService().build(session, sprint_id)
        except SprintNotFound:
            logger.warning("Sprint %s vanished before scorecard aggregation; skipping", sprint_id)
            return None
        except Exception:
            logger.error("Agent scorecard aggregation failed for sprint %s", sprint_id, exc_info=True)
            return None
        if not scorecard.scores:
            return None
        return render_agent_scorecard(scorecard)

    def _combine_summary(self, summary_text: Optional[str], scorecard_section: Optional[str]) -> Optional[str]:
        """Merge the Learnings summary and the scorecard section; either may be absent."""
        if summary_text and scorecard_section:
            return f"{summary_text}\n\n{scorecard_section}"
        return summary_text or scorecard_section

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _load_sprint_context(
        self,
        sprint_id: uuid.UUID,
        session: Optional[AsyncSession],
    ) -> tuple[Optional[LLCSprint], Optional[uuid.UUID]]:
        """Return (sprint_row, project_id). Falls back to None if no session."""
        if session is None:
            return None, None
        from sqlalchemy import select

        result = await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id))
        sprint = result.scalar_one_or_none()
        if sprint is None:
            return None, None
        return sprint, sprint.project_id

    async def _fetch_documents(self, collection_name: str) -> List[Dict[str, Any]]:
        """Return all documents from a ChromaDB collection as a list of dicts."""
        from knowledge import get_knowledge_base  # lazy — avoids chromadb at import time

        try:
            kb = await get_knowledge_base()
            col = await kb._async_chroma_client.get_collection(collection_name)
            raw = await col.get(include=["documents", "metadatas", "embeddings"])
        except Exception as exc:
            exc_msg = str(exc).lower()
            if "not found" in exc_msg or "does not exist" in exc_msg:
                logger.info(
                    "Collection %s does not exist; treating as empty",
                    collection_name,
                )
                return []
            logger.error(
                "Failed to fetch documents from %s: %s — archive will be skipped",
                collection_name,
                exc,
            )
            raise

        ids = raw.get("ids") or []
        documents = raw.get("documents") or []
        metadatas = raw.get("metadatas") or []
        embeddings = raw.get("embeddings") or []

        return [
            {
                "id": ids[i],
                "document": documents[i] if i < len(documents) else "",
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "embedding": embeddings[i] if i < len(embeddings) else None,
            }
            for i in range(len(ids))
        ]

    async def _direct_merge(
        self,
        docs: List[Dict[str, Any]],
        dst_collection: str,
        sprint_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> None:
        """Copy documents as-is into the destination collection."""
        from knowledge import get_knowledge_base  # lazy

        kb = await get_knowledge_base()
        dst = await kb._async_chroma_client.get_or_create_collection(
            name=dst_collection,
            metadata={"entity_type": "project", "entity_id": str(project_id)},
        )
        ids = [d["id"] for d in docs]
        texts = [d["document"] for d in docs]
        metadatas = [d["metadata"] for d in docs]
        embeddings = [d["embedding"] for d in docs]

        if any(e is not None for e in embeddings):
            await dst.upsert(ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings)
        else:
            await dst.upsert(ids=ids, documents=texts, metadatas=metadatas)

        logger.info("Direct-merged %d docs from sprint:%s into %s", len(docs), sprint_id, dst_collection)

    async def _llm_summarize_and_index(
        self,
        docs: List[Dict[str, Any]],
        dst_collection: str,
        sprint_id: uuid.UUID,
        project_id: uuid.UUID,
        sprint: Optional[LLCSprint] = None,
    ) -> str:
        """LLM-summarize docs and index the result into the destination collection."""
        combined = "\n---\n".join(d["document"] for d in docs if d["document"])
        if len(combined) > _MAX_PROMPT_CHARS:
            logger.warning(
                "Sprint %s combined docs (%d chars) exceed _MAX_PROMPT_CHARS=%d; truncating",
                sprint_id,
                len(combined),
                _MAX_PROMPT_CHARS,
            )
            combined = combined[:_MAX_PROMPT_CHARS]
        prompt = _SUMMARIZE_PROMPT.format(documents=combined)

        from services.llm_service import get_llm_service  # lazy

        llm = get_llm_service()
        try:
            response = await llm.chat(
                [{"role": "user", "content": prompt}],
                llm_type=LLMType.ANALYSIS,
                max_tokens=1024,
            )
        except Exception as exc:
            logger.error(
                "LLM summarization raised for sprint %s: %s — falling back to direct merge",
                sprint_id,
                exc,
            )
            await self._direct_merge(docs, dst_collection, sprint_id, project_id)
            return "[direct-merged: LLM summarization raised]"

        if response.error:
            logger.error("LLM summarization failed for sprint %s: %s", sprint_id, response.error)
            await self._direct_merge(docs, dst_collection, sprint_id, project_id)
            return "[direct-merged: LLM summarization failed]"

        summary_text: str = response.content or ""
        if not summary_text:
            logger.error(
                "LLM returned empty content for sprint %s; falling back to direct merge",
                sprint_id,
            )
            await self._direct_merge(docs, dst_collection, sprint_id, project_id)
            return "[direct-merged: LLM returned empty content]"
        closed_at = utc_timestamp()
        sprint_name = sprint.name if sprint else str(sprint_id)

        from knowledge import get_knowledge_base  # lazy

        kb = await get_knowledge_base()
        dst = await kb._async_chroma_client.get_or_create_collection(
            name=dst_collection,
            metadata={"entity_type": "project", "entity_id": str(project_id)},
        )
        doc_id = f"sprint_summary:{sprint_id}"
        await dst.upsert(
            ids=[doc_id],
            documents=[summary_text],
            metadatas=[
                {
                    "type": "sprint_summary",
                    "sprint_id": str(sprint_id),
                    "sprint_name": sprint_name,
                    "closed_at": closed_at,
                }
            ],
        )

        logger.info(
            "LLM-summarized %d docs from sprint:%s into %s (id=%s)",
            len(docs),
            sprint_id,
            dst_collection,
            doc_id,
        )
        return summary_text


def render_agent_scorecard(scorecard: SprintScorecard) -> str:
    """Render a ``SprintScorecard`` as a markdown section for the retro summary.

    Component signals (raw run/work-item counts) are shown alongside the
    composite ``reliability_score`` so the derivation stays inspectable
    rather than presenting a single opaque number.
    """
    header = [
        "## Agent Scorecard",
        "",
        "| Agent | Runs (terminal) | Success rate | Reliability (low-n aware) | Work items done | Spend (lifetime) |",
        "|---|---|---|---|---|---|",
    ]
    rows = [_render_scorecard_row(score) for score in scorecard.scores]
    return "\n".join(header + rows + ["", _render_scorecard_footnote(scorecard)])


def _render_scorecard_row(score: AgentScore) -> str:
    """Render one ``AgentScore`` as a markdown table row."""
    success = f"{score.success_rate:.1%}" if score.success_rate is not None else "n/a"
    reliability = f"{score.reliability_score:.2f}" if score.reliability_score is not None else "n/a"
    runs = str(score.runs_terminal) if score.runs_terminal is not None else "n/a"
    if score.low_sample:
        runs = f"{runs} (low-n)"
    spend = f"${score.spend_lifetime_usd:.2f}" if score.spend_lifetime_usd is not None else "n/a"
    name = score.agent_id or score.agent_name
    return f"| {name} | {runs} | {success} | {reliability} | {score.work_items_done} | {spend} |"


def _render_scorecard_footnote(scorecard: SprintScorecard) -> str:
    """Explain the run-window / spend-window caveats so the derivation is inspectable."""
    if scorecard.run_window_available:
        window = (
            f"Run window (approximate — time-windowed, not FK-linked; GH#12619): "
            f"{scorecard.run_window_start} to {scorecard.run_window_end}."
        )
    else:
        window = "Run-based metrics unavailable — sprint has no start_date."
    return f"{window} Spend is a lifetime total (not sprint-windowed) — see GH#13067."


__all__ = ["SprintKbSummarizer", "render_agent_scorecard"]
