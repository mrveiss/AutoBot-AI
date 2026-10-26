# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The knowledge-base read tools of :class:`tools.tool_registry.ToolRegistry`.

Split out of ``tool_registry.py`` (#16665) so that module does not grow. Both tools read as the
user the agent runs for (``user_id``); with no user they return nothing.
"""

from __future__ import annotations

from typing import Any, Dict

from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge.search_filters import filter_for_user_id


class KnowledgeReadToolsMixin:
    """``search_knowledge_base`` and ``get_fact``; needs ``self.logger`` and ``self._resolve_knowledge_base``."""

    async def search_knowledge_base(self, query: str, n_results: int = 5, user_id: str | None = None) -> Dict[str, Any]:
        """Agent tool: top-``n_results`` facts visible to ``user_id``, research quarantine excluded.

        No ``user_id`` returns no facts (#16665); an unavailable KB returns an error envelope.
        """
        kb = await self._resolve_knowledge_base()
        if not kb:
            return {
                "tool_name": "search_knowledge_base",
                "tool_args": {"query": query, "n_results": n_results},
                "result": "Knowledge base is not available",
                "status": "error",
            }

        try:
            # Issue #13024/#13027: canonical search() has no n_results kwarg.
            # Issue #13009: exclude quarantined research facts (#12622).
            results = await kb.search(query, top_k=n_results, filters=RESEARCH_QUARANTINE_FILTER)
            # #16665: the agent reads as the user it runs for; no user means no facts.
            results = await filter_for_user_id(results or [], kb, user_id)

            if results:
                formatted_results = []
                for result in results:
                    content_preview = (
                        result["content"][:200] + "..." if len(result["content"]) > 200 else result["content"]
                    )
                    metadata = result.get("metadata", {})
                    filename = metadata.get("filename", "N/A")
                    chunk_index = metadata.get("chunk_index", "N/A")
                    formatted_results.append(f"[{filename} - Chunk {chunk_index}]: " f"{content_preview}")

                result_text = f"Found {len(results)} relevant results:\n" + "\n".join(formatted_results)
            else:
                result_text = "No relevant information found in knowledge base"

            return {
                "tool_name": "search_knowledge_base",
                "tool_args": {"query": query, "n_results": n_results},
                "result": result_text,
                "status": "success",
            }
        except Exception as e:
            self.logger.error("Error searching knowledge base: %s", e)
            return {
                "tool_name": "search_knowledge_base",
                "tool_args": {"query": query, "n_results": n_results},
                "result": f"Error searching knowledge base: {e}",
                "status": "error",
            }

    async def get_fact(
        self, fact_id: int | None = None, query: str | None = None, user_id: str | None = None
    ) -> Dict[str, Any]:
        """Get facts from the knowledge base."""
        kb = await self._resolve_knowledge_base()
        if not kb:
            return {
                "tool_name": "get_fact",
                "tool_args": {"fact_id": fact_id, "query": query},
                "result": "Knowledge base is not available",
                "status": "error",
            }

        try:
            # Issue #788: get_fact() only accepts fact_id, use search() for queries
            if fact_id is not None:
                result = kb.get_fact(str(fact_id))
                results = [result] if result else []
            elif query:
                # Issue #13009: exclude quarantined research facts (#12622).
                results = await kb.search(query, top_k=5, filters=RESEARCH_QUARANTINE_FILTER)
            else:
                results = []
            # #16665: the agent reads as the user it runs for; no user means no facts.
            results = await filter_for_user_id(results, kb, user_id)

            if results:
                formatted_results = []
                for result in results:
                    rid = result.get("id", "N/A")
                    content = result.get("content", "No content")
                    formatted_results.append(f"Fact {rid}: {content}")

                result_text = "\n".join(formatted_results)
            else:
                result_text = "No facts found"

            return {
                "tool_name": "get_fact",
                "tool_args": {"fact_id": fact_id, "query": query},
                "result": result_text,
                "status": "success",
            }
        except Exception as e:
            self.logger.error("Error getting facts: %s", e)
            return {
                "tool_name": "get_fact",
                "tool_args": {"fact_id": fact_id, "query": query},
                "result": f"Error getting facts: {e}",
                "status": "error",
            }
