# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The workflow librarian step, split out of ``api/workflow.py`` (#16665) so that grandfathered module does not grow."""

from models.task_context import WorkflowStepContext


async def _handle_librarian_step(ctx: WorkflowStepContext) -> None:
    """Handle librarian agent step (Issue #336 - extracted handler)."""
    from agents.kb_librarian_agent import KBLibrarianAgent

    kb_agent = KBLibrarianAgent()
    search_query = ctx.action.replace("Search Knowledge Base", "").strip()
    if not search_query:
        search_query = "network security scanning tools"

    result = await kb_agent.process_query(search_query, user_id=ctx.user_id)  # #16665: the triggering user, else deny
    response = result.get("response", "Search completed")
    ctx.step["result"] = f"Knowledge base search completed: {response}"
