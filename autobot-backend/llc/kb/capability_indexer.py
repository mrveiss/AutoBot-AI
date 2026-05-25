# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Agent capability indexing into KB (GH#8244).

When agents are hired, their capabilities are indexed into the company's agents
collection ``company:{company_id}:agents`` so they can be discovered via RAG queries
(\"who can handle security audits?\", \"who has cloud devops experience?\").

On agent capability update or termination, documents are updated or deleted.
"""

import logging
from typing import Any, Dict, Optional

from autobot_shared.logging_manager import get_logger
from knowledge import get_knowledge_base

logger = get_logger(__name__)


async def _fetch_agent_row(agent_id: str, company_id: str) -> Optional[Dict[str, Any]]:
    """Read agent data from agent_org_nodes for capability indexing."""
    from sqlalchemy import text
    from llc.db import get_async_session_factory

    factory = get_async_session_factory()
    async with factory() as session:
        result = await session.execute(text("""
                SELECT aon.agent_id, aon.name, aon.title, aon.org_role,
                       aon.capabilities, aon.reports_to,
                       mgr.name AS manager_name
                FROM agent_org_nodes aon
                LEFT JOIN agent_org_nodes mgr ON mgr.agent_id = aon.reports_to
                WHERE aon.agent_id = :agent_id
                  AND aon.company_id = :company_id
            """).bindparams(agent_id=agent_id, company_id=company_id))
        row = result.mappings().first()
        return dict(row) if row else None


class AgentCapabilityIndexer:
    """Indexes agent capabilities into the company KB agents collection."""

    @classmethod
    def _collection_name(cls, company_id: str) -> str:
        """Return the canonical collection name for agent capabilities."""
        return f"company:{company_id}:agents"

    @classmethod
    def _doc_id(cls, agent_id: str) -> str:
        """Return the canonical document ID for an agent capability document."""
        return f"agent:{agent_id}"

    async def index(
        self,
        agent_id: str,
        company_id: str,
        agent_name: str,
        title: str,
        role: str,
        capabilities: str,
        manager_name: Optional[str] = None,
    ) -> str:
        """Index agent capabilities into the company agents collection.

        Reads agent name, title, role, capabilities text and creates a document
        in the company:agents collection keyed by agent_id. Old documents are
        deleted and new ones inserted (upsert).

        Args:
            agent_id: Unique agent identifier
            company_id: Company that owns the agent
            agent_name: Display name for the agent
            title: Agent's title/role
            role: Agent's functional role
            capabilities: Freetext description of capabilities
            manager_name: Optional manager name for reporting structure

        Returns:
            The document ID inserted (format: ``agent:{agent_id}``).
        """
        doc_id = self._doc_id(agent_id)

        # Compose capability document text
        doc_text = f"Agent {agent_name} ({title}) handles: {capabilities}."
        if manager_name:
            doc_text += f" Reports to: {manager_name}."

        meta: Dict[str, Any] = {
            "agent_id": agent_id,
            "company_id": company_id,
            "agent_name": agent_name,
            "title": title,
            "role": role,
        }
        if manager_name:
            meta["manager_name"] = manager_name

        await self._upsert(company_id, doc_id, doc_text, meta)
        return doc_id

    async def index_from_db(self, agent_id: str, company_id: str) -> Optional[str]:
        """Index agent capabilities by reading from agent_org_nodes.

        Convenience method for post-save hooks — fetches all required fields
        from the DB and delegates to :meth:`index`.

        Args:
            agent_id: Agent to index
            company_id: Company that owns the agent

        Returns:
            Document ID if indexed, or None if agent not found in DB.
        """
        row = await _fetch_agent_row(agent_id, company_id)
        if not row:
            logger.warning("Agent %s not found in agent_org_nodes; skipping capability index", agent_id)
            return None
        return await self.index(
            agent_id=agent_id,
            company_id=company_id,
            agent_name=row.get("name") or "",
            title=row.get("title") or "",
            role=row.get("org_role") or "",
            capabilities=row.get("capabilities") or "",
            manager_name=row.get("manager_name"),
        )

    async def remove(self, agent_id: str, company_id: str) -> None:
        """Remove agent capability document from the company agents collection.

        Called when agent is terminated or deleted.

        Args:
            agent_id: Agent to remove
            company_id: Company that owns the agent
        """
        doc_id = self._doc_id(agent_id)
        await self._delete(company_id, doc_id)

    async def _upsert(
        self,
        company_id: str,
        doc_id: str,
        content: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Upsert document into the company agents collection."""
        try:
            kb = await get_knowledge_base()
            collection_name = self._collection_name(company_id)
            collection = await kb._async_chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"entity_type": "company", "entity_id": company_id},
            )
            await collection.upsert(
                ids=[doc_id],
                documents=[content],
                metadatas=[metadata],
            )
            logger.info("Indexed agent capability: doc_id=%s, company_id=%s", doc_id, company_id)
        except Exception as e:
            logger.exception(
                "Failed to upsert agent capability %s for company %s: %s",
                doc_id,
                company_id,
                str(e),
            )

    async def _delete(
        self,
        company_id: str,
        doc_id: str,
    ) -> None:
        """Delete document from the company agents collection."""
        try:
            kb = await get_knowledge_base()
            collection_name = self._collection_name(company_id)
            try:
                collection = await kb._async_chroma_client.get_collection(collection_name)
            except Exception:
                logger.debug("Agent collection %s not found; nothing to delete", collection_name)
                return

            await collection.delete(ids=[doc_id])
            logger.info("Deleted agent capability: doc_id=%s, company_id=%s", doc_id, company_id)
        except Exception as e:
            logger.exception(
                "Failed to delete agent capability %s for company %s: %s",
                doc_id,
                company_id,
                str(e),
            )


__all__ = ["AgentCapabilityIndexer"]
