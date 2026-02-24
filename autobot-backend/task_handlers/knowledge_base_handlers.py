# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Task Handlers

Issue #322: Refactored to use TaskExecutionContext to eliminate data clump pattern.
"""

import logging
from typing import Any, Dict

from models.task_context import TaskExecutionContext

from .base import TaskHandler

logger = logging.getLogger(__name__)


class KBAddFileHandler(TaskHandler):
    """Handler for kb_add_file tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute knowledge base file addition with metadata and audit logging."""
        file_path = ctx.require_payload_value("file_path")
        file_type = ctx.require_payload_value("file_type")
        metadata = ctx.get_payload_value("metadata")

        result = await ctx.worker.knowledge_base.add_file(
            file_path, file_type, metadata
        )

        ctx.audit_log(
            "kb_add_file",
            result.get("status", "unknown"),
            {"file_path": file_path},
        )

        return result


class KBSearchHandler(TaskHandler):
    """Handler for kb_search tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute knowledge base search query with configurable result count."""
        query = ctx.require_payload_value("query")
        n_results = ctx.get_payload_value("n_results", 5)

        kb_results = await ctx.worker.knowledge_base.search(query, n_results)

        result = {
            "status": "success",
            "message": "KB search successful.",
            "results": kb_results,
        }

        ctx.audit_log(
            "kb_search",
            "success",
            {"query": query},
        )

        return result


class KBStoreFactHandler(TaskHandler):
    """Handler for kb_store_fact tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute knowledge base fact storage with optional metadata."""
        content = ctx.require_payload_value("content")
        metadata = ctx.get_payload_value("metadata")

        result = await ctx.worker.knowledge_base.store_fact(content, metadata)

        ctx.audit_log(
            "kb_store_fact",
            result.get("status", "unknown"),
            {"content_preview": content[:50]},
        )

        return result
