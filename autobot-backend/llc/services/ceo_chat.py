# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""CEO Chat service — company-scoped chat resolving to work objects (GH#8233).

#11501 T2: CeoChatService.send() now delegates to the shared chat pipeline
(chat_workflow) instead of a bespoke intent-classifier. The board LLM gets the
same experience as /chat and creates work objects by calling the LLC tools
(create_task / update_goal / request_approval / record_decision), which are
taught in the system prompt only when the request context carries a company_id.

Flow:
  1. Persist the human message.
  2. RAG-query the company + decisions KB for grounding (top 5 chunks).
  3. Delegate to ChatWorkflowManager.process_message_stream with
     {company_id, user_id} context; the LLC tools execute company-scoped.
  4. Persist the streamed reply; set resolved_entity_type/id from the tool
     result when the LLM created an entity.
"""

import logging
from typing import Any, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ceo_chat import LLCCeoChatMessage, LLCCeoChatThread
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

# #11501 T2: the bespoke phi3 intent-classifier (prompts, JSON extraction,
# intent dispatch) is retired — the board LLM now uses the shared chat pipeline
# + LLC tools. See CeoChatService._run_pipeline.

_AUTHOR_HUMAN = "human"
_AUTHOR_SYSTEM = "system"


def _get_workflow_manager():
    """Return the shared chat-workflow manager (#11501 T2).

    Wrapped so the heavy chat_workflow import is lazy and tests can patch this
    without importing the full pipeline.
    """
    from chat_workflow import get_chat_workflow_manager

    return get_chat_workflow_manager()


class CeoChatService(LLCServiceBase):
    """Service for LLC CEO Chat thread lifecycle and resolution."""

    # ------------------------------------------------------------------ CRUD

    async def create_thread(
        self,
        session: AsyncSession,
        company_id: str,
        title: str,
        *,
        created_by_user_id: Optional[str] = None,
    ) -> LLCCeoChatThread:
        thread = LLCCeoChatThread(
            company_id=company_id,
            title=title,
            created_by_user_id=created_by_user_id,
        )
        session.add(thread)
        await session.flush()
        return thread

    async def get_thread(
        self,
        session: AsyncSession,
        thread_id: str,
    ) -> Optional[LLCCeoChatThread]:
        result = await session.execute(select(LLCCeoChatThread).where(LLCCeoChatThread.id == thread_id))
        return result.scalar_one_or_none()

    async def list_threads(
        self,
        session: AsyncSession,
        company_id: str,
        *,
        limit: int = 50,
    ) -> List[LLCCeoChatThread]:
        result = await session.execute(
            select(LLCCeoChatThread)
            .where(LLCCeoChatThread.company_id == company_id)
            .order_by(LLCCeoChatThread.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------ Send

    async def send(
        self,
        session: AsyncSession,
        thread_id: str,
        message: str,
        user_id: Optional[str],
        *,
        company_name: str = "the company",
    ) -> LLCCeoChatMessage:
        """Process a human board message and return the system reply (#11501 T2).

        Steps:
          1. Persist the human message.
          2. RAG-query the company + decisions KB for grounding.
          3-6. Delegate to the shared chat pipeline (_run_pipeline): the board
             LLM answers and creates work objects via the LLC tools, then the
             reply is persisted and the thread resolution updated if an entity
             was created. company_name grounds the prompt.
        """
        # 1. Persist the incoming human message
        human_msg = LLCCeoChatMessage(
            thread_id=thread_id,
            author_type=_AUTHOR_HUMAN,
            author_user_id=user_id,
            body=message,
        )
        session.add(human_msg)
        await session.flush()

        # 2. RAG context — company KB + decisions KB (GH#8243)
        kb_chunks = await self._rag_query(thread_id, message)
        thread = await self.get_thread(session, thread_id)
        company_id = str(thread.company_id) if thread else "unknown"
        decision_chunks = await self._query_decisions(company_id, message)
        kb_chunks = kb_chunks + decision_chunks

        # 3-6. Delegate to the shared chat pipeline (#11501 T2). The board LLM
        # gets the same /chat experience and creates work objects via the LLC
        # tools (create_task/update_goal/request_approval/record_decision),
        # company-scoped from context. Retires the bespoke phi3 intent-classifier
        # that always fell back to "clarify" (KeyError('"intent"')).
        reply_body, entity_type, entity_id = await self._run_pipeline(
            thread_id=thread_id,
            message=message,
            company_id=company_id,
            user_id=user_id,
            kb_chunks=kb_chunks,
            company_name=company_name,
        )

        if entity_type and entity_id:
            await session.execute(
                update(LLCCeoChatThread)
                .where(LLCCeoChatThread.id == thread_id)
                .values(resolved_entity_type=entity_type, resolved_entity_id=entity_id)
            )

        system_msg = LLCCeoChatMessage(
            thread_id=thread_id,
            author_type=_AUTHOR_SYSTEM,
            author_user_id=None,
            body=reply_body,
        )
        session.add(system_msg)
        await session.flush()
        return system_msg

    async def _run_pipeline(
        self,
        *,
        thread_id: str,
        message: str,
        company_id: str,
        user_id: Optional[str],
        kb_chunks: List[str],
        company_name: str = "the company",
    ) -> tuple[str, Optional[str], Optional[str]]:
        """Run the board message through the shared chat pipeline (#11501 T2).

        Returns (reply_text, entity_type, entity_id). company_id/user_id go in
        the context so the LLC tools (create_task/...) execute company-scoped;
        the thread_id is the chat session_id. Company name + KB chunks are
        prepended as grounding. The created entity (if any) is read from the LLC
        tool-result metadata.

        Reply assembly (#11525 review): streaming ``response`` chunks are
        cumulative snapshots keyed by message id, so we keep the latest content
        per id and join distinct segments in order — robust whether the model
        ends with a single ``respond`` message or interleaves prose + thoughts.
        """
        grounded = f"[Company: {company_name}]\n"
        if kb_chunks:
            grounded += "Company context:\n" + "\n".join(kb_chunks[:5]) + "\n\n---\n\n"
        grounded += message
        context = {"company_id": company_id, "user_id": user_id or ""}

        responses: "dict[str, str]" = {}  # message-id → latest full content, in order
        entity_type: Optional[str] = None
        entity_id: Optional[str] = None
        manager = _get_workflow_manager()
        async for msg in manager.process_message_stream(thread_id, grounded, context):
            mtype = getattr(msg, "type", None)
            content = getattr(msg, "content", "") or ""
            meta = getattr(msg, "metadata", None) or {}
            if mtype == "response" and content:
                mid = getattr(msg, "id", None) or f"_seg{len(responses)}"
                responses[mid] = content  # snapshots replace; new segments append
            result = meta.get("result") if isinstance(meta, dict) else None
            if isinstance(result, dict) and result.get("entity_type") and result.get("entity_id"):
                entity_type = result["entity_type"]
                entity_id = result["entity_id"]

        reply = "\n\n".join(v for v in responses.values() if v).strip() or "Done."
        return reply, entity_type, entity_id

    # --------------------------------------------------------------- Helpers

    async def _rag_query(self, thread_id: str, message: str) -> List[str]:
        """Query the company KB and return up to 5 document chunks."""
        try:
            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            # The company KB collection is named "company:{company_id}"; we
            # infer company_id from the thread but fall back gracefully.
            collection_name = f"llc_kb_{thread_id}"
            try:
                collection = await client.get_collection(collection_name)
                results = await collection.query(
                    query_texts=[message],
                    n_results=5,
                )
                docs: Any = results.get("documents", [[]])
                return docs[0] if docs else []
            except Exception:
                # Collection may not exist yet — not fatal.
                return []
        except Exception as exc:
            logger.warning("RAG query failed for ceo_chat thread %s: %s", thread_id, exc)
            return []

    async def _query_decisions(self, company_id: str, message: str) -> List[str]:
        """Query the decisions KB and return relevant past decision texts (GH#8243)."""
        try:
            from ..kb.decision_log import DecisionLogReader

            reader = DecisionLogReader()
            results = await reader.search(company_id=company_id, query=message, n_results=3)
            return [r["text"] for r in results if r.get("text")]
        except Exception as exc:
            logger.warning("Decisions RAG query failed for company %s: %s", company_id, exc)
            return []
