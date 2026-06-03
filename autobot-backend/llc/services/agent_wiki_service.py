# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC AgentWikiService — CRUD for per-agent knowledge wiki (GH#9021)."""

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..models.agent_wiki import LLCAgentWikiEntry

logger = get_logger(__name__)


class AgentWikiService:
    async def list_entries(
        self,
        session: AsyncSession,
        agent_id: str,
        company_id: uuid.UUID,
        namespace: Optional[str] = None,
    ) -> List[LLCAgentWikiEntry]:
        stmt = select(LLCAgentWikiEntry).where(
            LLCAgentWikiEntry.agent_id == agent_id,
            LLCAgentWikiEntry.company_id == company_id,
        )
        if namespace:
            stmt = stmt.where(LLCAgentWikiEntry.namespace == namespace)
        stmt = stmt.order_by(LLCAgentWikiEntry.namespace, LLCAgentWikiEntry.key)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_entry(
        self,
        session: AsyncSession,
        entry_id: uuid.UUID,
        agent_id: str,
        company_id: uuid.UUID,
    ) -> Optional[LLCAgentWikiEntry]:
        result = await session.execute(
            select(LLCAgentWikiEntry).where(
                LLCAgentWikiEntry.id == entry_id,
                LLCAgentWikiEntry.agent_id == agent_id,
                LLCAgentWikiEntry.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_entry(
        self,
        session: AsyncSession,
        agent_id: str,
        company_id: uuid.UUID,
        namespace: str,
        key: str,
        title: str,
        body: str,
    ) -> LLCAgentWikiEntry:
        entry = LLCAgentWikiEntry(
            agent_id=agent_id,
            company_id=company_id,
            namespace=namespace,
            key=key,
            title=title,
            body=body,
        )
        session.add(entry)
        await session.flush()
        await session.refresh(entry)
        logger.info("Created wiki entry %s for agent %s ns=%s key=%s", entry.id, agent_id, namespace, key)
        return entry

    async def update_entry(
        self,
        session: AsyncSession,
        entry: LLCAgentWikiEntry,
        title: Optional[str] = None,
        body: Optional[str] = None,
        namespace: Optional[str] = None,
        key: Optional[str] = None,
    ) -> LLCAgentWikiEntry:
        if title is not None:
            entry.title = title
        if body is not None:
            entry.body = body
        if namespace is not None:
            entry.namespace = namespace
        if key is not None:
            entry.key = key
        await session.flush()
        await session.refresh(entry)
        return entry

    async def delete_entry(self, session: AsyncSession, entry: LLCAgentWikiEntry) -> None:
        await session.delete(entry)
        await session.flush()

    async def get_wiki_context(
        self,
        session: AsyncSession,
        agent_id: str,
        company_id: uuid.UUID,
    ) -> str:
        """Return all wiki entries for an agent formatted as system-context Markdown."""
        entries = await self.list_entries(session, agent_id, company_id)
        if not entries:
            return ""
        sections: List[str] = ["## Agent Knowledge Wiki\n"]
        current_ns = None
        for entry in entries:
            if entry.namespace != current_ns:
                current_ns = entry.namespace
                sections.append(f"\n### {current_ns}\n")
            sections.append(f"**{entry.title}**\n{entry.body}\n")
        return "\n".join(sections)
