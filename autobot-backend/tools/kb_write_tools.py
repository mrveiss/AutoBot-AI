# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The knowledge-base write tools of :class:`tools.tool_registry.ToolRegistry`.

Split out of ``tool_registry.py`` (#19517) so that module shrinks. The metadata an agent
passes is the LLM's text, not the user's: both tools write inside
:func:`knowledge.write_scope.agent_write_scope`, so ``KnowledgeBase.store_fact`` drops any
ownership or visibility it names and stamps the turn's signed-in user instead. A turn with no
signed-in user is refused (``KbWriteDenied``) and reported as an error.
"""

from __future__ import annotations

from typing import Any, Dict

from knowledge.write_scope import agent_write_scope

_KB_UNAVAILABLE = "Knowledge base is not available"


class KnowledgeWriteToolsMixin:
    """``add_file_to_knowledge_base`` and ``store_fact``; needs ``self.logger`` and ``self._resolve_knowledge_base``."""

    async def add_file_to_knowledge_base(
        self, file_path: str, file_type: str, metadata: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Add a file to the knowledge base."""
        name = "add_file_to_knowledge_base"
        args = {"file_path": file_path, "file_type": file_type, "metadata": metadata}
        kb = await self._resolve_knowledge_base()
        if not kb:
            return {"tool_name": name, "tool_args": {"file_path": file_path, "file_type": file_type},
                    "result": _KB_UNAVAILABLE, "status": "error"}  # fmt: skip
        try:
            with agent_write_scope():
                result = await kb.add_file(file_path, file_type, metadata or {})
            message = result.get("message", f"File {file_path} added to knowledge base")
            return {"tool_name": name, "tool_args": args, "result": message, "status": result.get("status", "success")}
        except Exception as e:
            self.logger.error("Error adding file to knowledge base: %s", e)
            return {"tool_name": name, "tool_args": args,
                    "result": f"Error adding file to knowledge base: {e}", "status": "error"}  # fmt: skip

    async def store_fact(self, content: str, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Store a fact in the knowledge base."""
        args = {"content": content, "metadata": metadata}
        kb = await self._resolve_knowledge_base()
        if not kb:
            return {"tool_name": "store_fact", "tool_args": args, "result": _KB_UNAVAILABLE, "status": "error"}
        try:
            with agent_write_scope():
                result = await kb.store_fact(content, {**(metadata or {}), "ingest_route": "agent_tool"})
            message = result.get("message", "Fact stored successfully")
            return {"tool_name": "store_fact", "tool_args": args, "result": message,
                    "status": result.get("status", "success")}  # fmt: skip
        except Exception as e:
            self.logger.error("Error storing fact: %s", e)
            return {
                "tool_name": "store_fact",
                "tool_args": args,
                "result": f"Error storing fact: {e}",
                "status": "error",
            }
