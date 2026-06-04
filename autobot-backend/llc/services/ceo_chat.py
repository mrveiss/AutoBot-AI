# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""CEO Chat service — company-scoped chat resolving to work objects (GH#8233).

CeoChatService.send() flow:
  1. RAG-query ``company:{company_id}`` KB collection with message text (top 5).
  2. Call LLM via ``llm_shared`` with board-interface system prompt.
  3. Interpret structured JSON response → call appropriate LLC service.
  4. Persist resolution in ``resolved_entity_type`` + ``resolved_entity_id``.
  5. Return system reply message with link to the resolved entity.

Resolution intents:
  create_task        → WorkItemService.create()
  update_goal        → GoalService.update()
  request_approval   → ApprovalService.create()
  record_decision    → stored as thread annotation (resolved_entity_type="decision")
  clarify            → no entity created; asks for more info
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ceo_chat import LLCCeoChatMessage, LLCCeoChatThread
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_BOARD_SYSTEM_PROMPT = (
    "You are the board interface for {company_name}. "
    "Your goal is to resolve this message into one of: "
    "[create_task, update_goal, request_approval, record_decision, clarify]. "
    "Return structured JSON with keys: "
    '{"intent": "<one of the above>", "summary": "<brief>", "entity": {<relevant fields>}}. '
    "Respond ONLY with valid JSON."
)

_AUTHOR_HUMAN = "human"
_AUTHOR_SYSTEM = "system"


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
        """Process a human message and return the system reply.

        Steps:
          1. Persist the human message.
          2. RAG-query the company KB for context.
          3. Call LLM to resolve the intent.
          4. Call the appropriate LLC service for non-clarify intents.
          5. Update thread resolution fields.
          6. Persist and return the system reply message.
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

        # 3. LLM resolution
        resolution = await self._resolve_via_llm(
            message=message,
            kb_chunks=kb_chunks,
            company_name=company_name,
            conversation_id=thread_id,
        )

        # 4. Act on resolved intent (company_id resolved above in step 2)
        entity_type, entity_id = await self._dispatch_intent(
            session=session,
            company_id=company_id,
            resolution=resolution,
        )

        # 5. Update thread resolution fields when we created/updated an entity
        if entity_type and entity_id:
            await session.execute(
                update(LLCCeoChatThread)
                .where(LLCCeoChatThread.id == thread_id)
                .values(
                    resolved_entity_type=entity_type,
                    resolved_entity_id=entity_id,
                )
            )

        # 6. Build and persist system reply
        reply_body = self._build_reply(resolution, entity_type, entity_id)
        system_msg = LLCCeoChatMessage(
            thread_id=thread_id,
            author_type=_AUTHOR_SYSTEM,
            author_user_id=None,
            body=reply_body,
        )
        session.add(system_msg)
        await session.flush()
        return system_msg

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

    async def _resolve_via_llm(
        self,
        *,
        message: str,
        kb_chunks: List[str],
        company_name: str,
        conversation_id: str,
    ) -> Dict[str, Any]:
        """Call the LLM and return parsed resolution dict."""
        try:
            from llm_shared.types import LLMType
            from services.llm_service import get_llm_service

            svc = get_llm_service()
            context = "\n".join(kb_chunks) if kb_chunks else ""
            system_prompt = _BOARD_SYSTEM_PROMPT.format(company_name=company_name)

            messages: List[Dict[str, str]] = []
            if context:
                messages.append({"role": "system", "content": f"{system_prompt}\n\nContext:\n{context}"})
            else:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": message})

            response = await svc.chat(
                messages=messages,
                conversation_id=conversation_id,
                llm_type=LLMType.EXTRACTION,
            )

            raw = (response.content or "").strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as exc:
            logger.warning("LLM resolution failed: %s", exc)
            return {"intent": "clarify", "summary": str(exc), "entity": {}}

    async def _dispatch_intent(
        self,
        *,
        session: AsyncSession,
        company_id: str,
        resolution: Dict[str, Any],
    ) -> tuple[Optional[str], Optional[uuid.UUID]]:
        """Call the appropriate LLC service and return (entity_type, entity_id)."""
        intent = resolution.get("intent", "clarify")
        entity_data = resolution.get("entity", {})

        try:
            if intent == "create_task":
                from ..models.enums import WorkItemPriority, WorkItemType
                from .work_item_service import WorkItemService

                item_svc = WorkItemService()
                item = await item_svc.create(
                    session,
                    company_id=company_id,
                    type=WorkItemType.TASK,
                    title=entity_data.get("title", resolution.get("summary", "CEO Chat Task")),
                    description=entity_data.get("description"),
                    priority=WorkItemPriority(entity_data.get("priority", "medium")),
                )
                return "work_item", item.id

            if intent == "update_goal":
                goal_id = entity_data.get("goal_id")
                if goal_id:
                    from .goal import GoalService

                    goal_svc = GoalService()
                    updates = {k: v for k, v in entity_data.items() if k != "goal_id"}
                    await goal_svc.update(session, goal_id=goal_id, **updates)
                    return "goal", uuid.UUID(goal_id)

            if intent == "request_approval":
                from ..models.enums import ApprovalType
                from .approval import ApprovalService

                appr_svc = ApprovalService()
                appr = await appr_svc.create(
                    session,
                    company_id=company_id,
                    type=ApprovalType(entity_data.get("type", "general")),
                    requested_by_agent_id=entity_data.get("agent_id", str(uuid.uuid4())),
                    payload=entity_data,
                )
                return "approval", appr.id

            if intent == "record_decision":
                # No external service call — the thread itself is the record.
                return "decision", None

        except Exception as exc:
            logger.warning("Intent dispatch failed for intent=%s: %s", intent, exc)

        return None, None

    @staticmethod
    def _build_reply(
        resolution: Dict[str, Any],
        entity_type: Optional[str],
        entity_id: Optional[uuid.UUID],
    ) -> str:
        intent = resolution.get("intent", "clarify")
        summary = resolution.get("summary", "")

        if intent == "clarify":
            return f"Could you clarify? {summary}"

        if not entity_type:
            return f"Resolved as '{intent}': {summary} (no entity created due to missing context)."

        if entity_id:
            return f"Resolved as '{intent}': {summary}. Created {entity_type} [{entity_id}]."

        return f"Resolved as '{intent}': {summary}. Recorded as {entity_type}."
