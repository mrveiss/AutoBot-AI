# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Task Handlers

Issue #322: Refactored to use TaskExecutionContext to eliminate data clump pattern.
"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.models.task_result import task_success
from knowledge.search_filters import filter_for_user_id
from knowledge.write_scope import caller_write_scope
from models.task_context import TaskExecutionContext

from .base import TaskHandler

logger = get_logger(__name__)


class KBAddFileHandler(TaskHandler):
    """Handler for kb_add_file tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute knowledge base file addition with metadata and audit logging."""
        file_path = ctx.require_payload_value("file_path")
        file_type = ctx.require_payload_value("file_type")
        metadata = ctx.get_payload_value("metadata")

        kb = await ctx.worker.resolve_knowledge_base()
        with caller_write_scope(ctx.metadata.get("user_id"), ctx.metadata.get("org_id")):  # #19517
            result = await kb.add_file(file_path, file_type, metadata)

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

        kb = await ctx.worker.resolve_knowledge_base()
        kb_results = await kb.search(query, n_results)
        # #16665: the task's triggering user, stamped by the orchestration layer in ctx.metadata -- never the
        # payload, which a caller controls. No user, no results.
        kb_results = await filter_for_user_id(kb_results, kb, ctx.metadata.get("user_id"))

        result = task_success("KB search successful.", data={"results": kb_results})

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

        kb = await ctx.worker.resolve_knowledge_base()
        with caller_write_scope(ctx.metadata.get("user_id"), ctx.metadata.get("org_id")):  # #19517
            result = await kb.store_fact(content, metadata)

        ctx.audit_log(
            "kb_store_fact",
            result.get("status", "unknown"),
            {"content_preview": content[:50]},
        )

        return result
