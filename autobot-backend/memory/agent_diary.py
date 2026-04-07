# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AgentDiaryService — per-agent cross-session journal stored as KB facts.

Each diary entry is a KB fact whose metadata carries the agent_name,
session_id, and topic so entries can be retrieved or searched per agent
without touching any other KB content.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def _get_kb():
    """Module-level thin wrapper so tests can patch ``memory.agent_diary._get_kb``."""
    from knowledge._composed import get_knowledge_base

    return await get_knowledge_base()


class AgentDiaryService:
    """Persistent per-agent journal backed by the knowledge base.

    Entries are stored as KB facts with category ``AGENT_DIARY`` and
    ``source`` set to the agent name so they are easily filtered.

    Usage::

        diary = AgentDiaryService()
        fact_id = await diary.write("my_agent", session_id, "processed X", topic="work")
        entries  = await diary.read("my_agent", last_n=20)
        hits     = await diary.search("my_agent", "processed X")
    """

    CATEGORY = "AGENT_DIARY"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def write(
        self,
        agent_name: str,
        session_id: str,
        entry: str,
        topic: str = "general",
    ) -> str:
        """Write a journal entry as a KB fact.

        Args:
            agent_name: Logical name of the agent (used as fact source).
            session_id:  Current processing session identifier.
            entry:       Free-text diary content to persist.
            topic:       Optional topic tag for grouping entries.

        Returns:
            fact_id of the created (or duplicate) KB fact, or ``""`` on error.
        """
        try:
            kb = await _get_kb()
            metadata: Dict[str, Any] = {
                "category": self.CATEGORY,
                "source": agent_name,
                "agent_name": agent_name,
                "session_id": session_id,
                "topic": topic,
                "diary_timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }
            result = await kb.store_fact(content=entry, metadata=metadata)
            fact_id: str = result.get("fact_id", "")
            logger.debug(
                "AgentDiary write: agent=%s session=%s fact_id=%s status=%s",
                agent_name,
                session_id,
                fact_id,
                result.get("status"),
            )
            return fact_id
        except Exception as exc:
            logger.warning(
                "AgentDiary write failed for agent=%s: %s", agent_name, exc
            )
            return ""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def read(self, agent_name: str, last_n: int = 10) -> List[Dict[str, Any]]:
        """Return the last *last_n* diary entries for *agent_name*, newest first.

        Uses a metadata-filtered listing (``get_all_facts``) rather than
        semantic search so that all entries are deterministically retrieved
        regardless of their semantic similarity to a query string.

        Args:
            agent_name: Agent whose entries to retrieve.
            last_n:     Maximum number of entries to return.

        Returns:
            List of fact dicts sorted newest-first (may be empty on error).
        """
        try:
            kb = await _get_kb()
            all_facts = await kb.get_all_facts()
            entries = [
                f for f in all_facts
                if (f.get("metadata") or {}).get("category") == self.CATEGORY
                and (f.get("metadata") or {}).get("source") == agent_name
            ]
            entries.sort(
                key=lambda r: r.get("metadata", {}).get("diary_timestamp", ""),
                reverse=True,
            )
            return entries[:last_n]
        except Exception as exc:
            logger.warning(
                "AgentDiary read failed for agent=%s: %s", agent_name, exc
            )
            return []

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self, agent_name: str, query: str, n: int = 5
    ) -> List[Dict[str, Any]]:
        """Semantic search within one agent's diary.

        Args:
            agent_name: Agent whose diary to search.
            query:      Free-text search query.
            n:          Maximum number of results.

        Returns:
            List of matching result dicts, or empty list on error.
        """
        try:
            kb = await _get_kb()
            filters = {"source": agent_name, "category": self.CATEGORY}
            results = await kb.search(query=query, top_k=n, filters=filters)
            return results[:n]
        except Exception as exc:
            logger.warning(
                "AgentDiary search failed for agent=%s query=%r: %s",
                agent_name,
                query,
                exc,
            )
            return []


__all__ = ["AgentDiaryService"]
