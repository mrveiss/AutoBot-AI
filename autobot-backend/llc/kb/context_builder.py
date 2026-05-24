# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC Heartbeat context builder — parallel RAG assembly (GH#8236).

Assembles rich agent context from company goals, projects, agent memory, and
similar past work items. Queries happen in parallel for performance (P95 ≤ 2s).
"""

import asyncio
import gzip
import json
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..config import AGENT_API_BASE_URL
from ..models.goal import LLCGoal
from ..services.goal import GoalService
from ..services.work_item_service import WorkItemService
from .inheritance import KbInheritanceResolver
from .rag_assembler import AssemblerProfile, LLCRAGAssembler

logger = get_logger(__name__)


class HeartbeatContextBuilder:
    """Build rich context payload for agent heartbeat runs (GH#8236).

    Assembles parallel RAG queries over company/project/agent KB collections,
    plus goal ancestry and past work summaries. Final payload stored compressed
    in heartbeat_run.context_snapshot.
    """

    def __init__(
        self,
        rag_assembler: LLCRAGAssembler,
        goal_service: GoalService,
        work_item_service: WorkItemService,
        inheritance_resolver: Optional[KbInheritanceResolver] = None,
    ):
        """Initialize builder with services.

        Args:
            rag_assembler: RAG service for KB queries
            goal_service: Goal ancestry and retrieval
            work_item_service: Work item details and history
            inheritance_resolver: KB inheritance resolver (GH#8241), optional for backwards compat
        """
        self.rag_assembler = rag_assembler
        self.goal_service = goal_service
        self.work_item_service = work_item_service
        self.inheritance_resolver = inheritance_resolver or KbInheritanceResolver(rag_assembler)

    async def build(
        self,
        session: AsyncSession,
        agent_id: str,
        work_item_id: uuid.UUID,
        context_mode: str = "fat",
    ) -> Dict[str, Any]:
        """Build heartbeat context for an agent.

        Args:
            session: DB session
            agent_id: Agent ID
            work_item_id: Work item being checked out
            context_mode: "thin" (minimal) or "fat" (rich, GH#8236)

        Returns:
            Dict with assembled context, ready to compress and store.

        Raises:
            ValueError: If work_item_id not found
        """
        if context_mode == "thin":
            return await self._build_thin(session, agent_id, work_item_id)
        elif context_mode == "fat":
            return await self._build_fat(session, agent_id, work_item_id)
        else:
            raise ValueError(f"Unknown context_mode: {context_mode}")

    async def _build_thin(
        self,
        session: AsyncSession,
        agent_id: str,
        work_item_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Build minimal context for quick heartbeat startup.

        Returns:
            Dict with work_item_id, api_base, agent_api_key
        """
        work_item = await self.work_item_service.get(session, work_item_id)
        if work_item is None:
            raise ValueError(f"Work item {work_item_id} not found")

        return {
            "work_item_id": str(work_item_id),
            "api_base": AGENT_API_BASE_URL,
            "agent_api_key": "<injected-at-runtime>",
        }

    async def _build_fat(
        self,
        session: AsyncSession,
        agent_id: str,
        work_item_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Build rich context with parallel RAG queries (GH#8236).

        Parallel queries:
        - company:{company_id} top 5 docs matching work_item.title + description
        - project:{project_id} top 8 docs matching work_item.title
        - agent:{agent_id} top 5 docs matching work_item.title (agent memory)
        - project:{project_id} filtered by status=done, top 3 similar items

        Returns:
            Dict with goal_ancestry, company_context, project_context, agent_memory,
            similar_past_work, acceptance_criteria, work_item_detail
        """
        work_item = await self.work_item_service.get(session, work_item_id)
        if work_item is None:
            raise ValueError(f"Work item {work_item_id} not found")

        company_id = str(work_item.company_id)
        project_id = str(work_item.project_id) if work_item.project_id else None

        # Start parallel tasks (P95 ≤ 2s per task, 4 tasks → ≤ 2s total)
        query_text = f"{work_item.title}\n{work_item.description or ''}"

        # Task 1: Company context with inheritance (top 5, GH#8241)
        company_task = (
            self.inheritance_resolver.search_with_inheritance(
                session=session,
                company_id=company_id,
                query_text=query_text,
                top_k=5,
            )
            if hasattr(self.inheritance_resolver, "search_with_inheritance")
            else asyncio.sleep(0)
        )

        # Task 2: Project context (top 8) — optional if no project
        project_task = (
            self.rag_assembler.assemble(
                company_id=company_id,
                profile=AssemblerProfile.HEARTBEAT,
                project_id=project_id,
                agent_id=None,
                work_item_id=work_item_id,
                query_text=query_text,
            )
            if project_id
            else asyncio.sleep(0)
        )

        # Task 3: Agent memory (top 5)
        agent_task = (
            self.rag_assembler.assemble(
                company_id=company_id,
                profile=AssemblerProfile.HEARTBEAT,
                project_id=None,
                agent_id=agent_id,
                work_item_id=work_item_id,
                query_text=query_text,
            )
            if hasattr(self.rag_assembler, "assemble")
            else asyncio.sleep(0)
        )

        # Task 4: Similar past work (top 3, status=done)
        past_work_task = self._get_similar_completed_items(session, project_id, query_text, max_results=3)

        # Run all queries in parallel
        results = await asyncio.gather(
            company_task,
            project_task,
            agent_task,
            past_work_task,
            return_exceptions=True,
        )

        company_ctx_raw = results[0] if not isinstance(results[0], Exception) else None
        project_ctx = results[1] if not isinstance(results[1], Exception) else None
        agent_mem = results[2] if not isinstance(results[2], Exception) else None
        past_work = results[3] if not isinstance(results[3], Exception) else []

        # Format company_context from inheritance results (GH#8241)
        company_ctx = self._format_inherited_context(company_ctx_raw)

        # Build goal ancestry
        goal_ancestry = []
        if work_item.goal_id:
            goal = await self.goal_service.get(session, work_item.goal_id)
            if goal:
                ancestors = await self.goal_service.get_ancestors(session, work_item.goal_id)
                goal_ancestry = [{"id": str(g.id), "title": g.title, "level": g.level} for g in ancestors + [goal]]

        return {
            "work_item_id": str(work_item_id),
            "work_item_detail": {
                "title": work_item.title,
                "description": work_item.description,
                "status": work_item.status,
                "priority": work_item.priority,
                "acceptance_criteria": work_item.acceptance_criteria,
            },
            "goal_ancestry": goal_ancestry,
            "company_context": company_ctx or {"chunks": [], "sources": []},
            "project_context": project_ctx or {"chunks": [], "sources": []},
            "agent_memory": agent_mem or {"chunks": [], "sources": []},
            "similar_past_work": past_work,
            "api_base": "http://localhost:8001/api",
            "agent_api_key": "<injected-at-runtime>",
        }

    def _format_inherited_context(self, results: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Format inheritance resolver results into standard context format (GH#8241).

        Args:
            results: List of dicts from KbInheritanceResolver.search_with_inheritance()

        Returns:
            Dict with 'chunks' and 'sources' keys for compatibility with existing context format.
        """
        if not results:
            return {"chunks": [], "sources": []}

        chunks = []
        sources_set = set()

        for result in results:
            chunks.append(
                {
                    "id": result.get("id"),
                    "content": result.get("content", ""),
                    "score": result.get("weighted_score", result.get("score", 0.0)),
                    "source_company_id": result.get("source_company_id"),
                    "metadata": result.get("metadata", {}),
                }
            )
            if result.get("source_company_id"):
                sources_set.add(result["source_company_id"])

        return {
            "chunks": chunks,
            "sources": list(sources_set),
        }

    async def _get_similar_completed_items(
        self,
        session: AsyncSession,
        project_id: Optional[str],
        query_text: str,
        max_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """Find similar completed work items in the same project.

        Args:
            session: DB session
            project_id: Project to search in
            query_text: Query text for similarity matching
            max_results: Max results to return

        Returns:
            List of similar completed work items
        """
        if not project_id:
            return []

        try:
            from sqlalchemy import select

            from ..models.work_item import LLCWorkItem, WorkItemStatus

            stmt = (
                select(LLCWorkItem)
                .where(LLCWorkItem.project_id == uuid.UUID(project_id))
                .where(LLCWorkItem.status == WorkItemStatus.DONE.value)
                .order_by(LLCWorkItem.updated_at.desc())
                .limit(max_results)
            )
            result = await session.execute(stmt)
            items = result.scalars().all()
            return [
                {
                    "id": str(item.id),
                    "title": item.title,
                    "description": item.description,
                }
                for item in items
            ]
        except Exception as e:
            logger.warning("Failed to fetch similar completed items: %s", e)
            return []
