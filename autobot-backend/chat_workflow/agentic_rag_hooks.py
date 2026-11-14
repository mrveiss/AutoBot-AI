# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Extension and plugin hooks around the agentic RAG pre-fetch node.

Split out of ``chat_workflow.graph.perform_knowledge_search`` (#16664) to keep that node under the
function-length limit -- a move, not a behaviour change. Both hooks are non-fatal: a failing
extension never breaks the turn.
"""

from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def emit_after_rag_results(context_str: str, user_query: str, session_id: Any) -> str:
    """Run the AFTER_RAG_RESULTS hook over *context_str* and return the context it leaves. Issue #4263."""
    from chat_workflow.session_handler import _emit_after_rag_results

    try:
        # Convert context_str back to results format for extensions
        # Results format: list of dicts with content/metadata
        results = [{"content": context_str}] if context_str else []
        results = await _emit_after_rag_results(results, user_query, session_id, {})
        # Reconstruct context_str from filtered results
        return "\n\n".join([r.get("content", "") for r in results if r.get("content")])
    except Exception as hook_exc:  # noqa: BLE001
        logger.debug("AFTER_RAG_RESULTS hook failed (non-fatal): %s", hook_exc)
        return context_str


async def notify_kb_search(session_id: Any, query: str, context_length: int) -> None:
    """Notify plugins after a knowledge base search. Issue #3278."""
    try:
        from autobot_shared.plugin_sdk import Hook, HookRegistry

        await HookRegistry().call_hook(
            Hook.ON_KB_SEARCH.value,
            session_id=session_id,
            query=query,
            context_length=context_length,
        )
    except Exception as _hook_exc:  # noqa: BLE001
        logger.debug("Plugin hook ON_KB_SEARCH failed (non-fatal): %s", _hook_exc)
