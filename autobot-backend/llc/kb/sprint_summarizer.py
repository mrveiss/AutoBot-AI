# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Sprint KB summarizer — LLM-summarize and merge into project KB on close (GH#8238).

On sprint close:
  1. Fetch all documents from ``sprint:{sprint_id}`` ChromaDB collection.
  2. ≤ 10 docs  → merge directly into ``project:{project_id}`` (no LLM call).
  3. > 10 docs  → LLM-summarize then index the summary into ``project:{project_id}``.
  4. Store the summary text on the sprint row (``kb_summary`` column).
  5. Archive the sprint collection via KbCollectionManager.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..kb.collections import KbCollectionManager
from ..models.sprint import LLCSprint

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
            await self._km.archive_collection(KbCollectionManager.SPRINT_PREFIX, sprint_id)
            return None

        sprint, project_id = await self._load_sprint_context(sprint_id, session)

        if project_id is None:
            logger.warning(
                "Sprint %s has no parent project in DB; skipping KB merge",
                sprint_id,
            )
            await self._km.archive_collection(KbCollectionManager.SPRINT_PREFIX, sprint_id)
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
                "Write to project KB failed for sprint %s — archive skipped to prevent data loss",
                sprint_id,
            )
            raise

        await self._km.archive_collection(KbCollectionManager.SPRINT_PREFIX, sprint_id)

        if summary_text and session is not None and sprint is not None:
            sprint.kb_summary = summary_text  # type: ignore[attr-defined]
            await session.flush()

        return summary_text

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
                llm_type="summarization",
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
        closed_at = datetime.now(timezone.utc).isoformat()
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


__all__ = ["SprintKbSummarizer"]
