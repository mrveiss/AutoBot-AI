# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AI Stack multi-agent orchestration -- dispatch and coordination helpers.

Split out of ``api/ai_stack_integration.py`` (#16716) to bring that file back
under ``scripts/check_python_file_size.py``'s ceiling after #16716's own
earlier commit (removing an admin RAG/chat read-bypass, #16654/#16745) grew
it past the ceiling a prior commit on this branch had wrongly raised instead
of splitting -- the same fix #16895 applied to ``facts.py`` via
``FactSharingMixin``: "a file growing never justifies [raising the ceiling]...
split, don't raise it."

This is the per-agent-type query dispatch table (Issue #336), the
parallel/sequential coordination helpers (Issue #315), and the
``/orchestrate/multi-agent-query`` route itself -- a self-contained unit with
no other AI Stack endpoint depending on it. ``api/ai_stack_integration.py``
mounts this module's router onto its own via ``router.include_router(...)``,
the same composition ``api/analytics.py`` uses for its own extracted
sub-routers (``analytics_code.py``, ``analytics_cost.py``, etc.), so both
still answer under the one ``/ai-stack`` prefix and ``ai-stack`` tag.
``multi_agent_query`` is re-exported from ``api.ai_stack_integration`` too,
so existing ``from api.ai_stack_integration import multi_agent_query`` call
sites keep working unchanged.
"""

from typing import Any, Awaitable, Callable, Dict, List

from fastapi import APIRouter, Depends

from api.schemas_agent import MultiAgentQueryData
from api.schemas_common import DataResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from services.ai_stack_client import get_ai_stack_client
from utils.response_helpers import create_success_response

# Type alias for agent handlers (Issue #336)
AgentQueryHandler = Callable[[Any, str], Awaitable[Dict[str, Any]]]

router = APIRouter(tags=["ai-stack"])


async def _query_rag_agent(ai_client: Any, query: str) -> Dict[str, Any]:
    """Query RAG agent (Issue #336 - extracted handler)."""
    return await ai_client.rag_query(query=query, max_results=5)


async def _query_research_agent(ai_client: Any, query: str) -> Dict[str, Any]:
    """Query research agent (Issue #336 - extracted handler)."""
    return await ai_client.research_query(query=query)


async def _query_classification_agent(ai_client: Any, query: str) -> Dict[str, Any]:
    """Query classification agent (Issue #336 - extracted handler)."""
    return await ai_client.classify_content(content=query)


async def _query_chat_agent(ai_client: Any, query: str) -> Dict[str, Any]:
    """Query chat agent (Issue #336 - extracted handler)."""
    return await ai_client.chat_message(message=query)


# Issue #336: Dispatch table for agent query handlers
AGENT_QUERY_HANDLERS: Dict[str, AgentQueryHandler] = {
    "rag": _query_rag_agent,
    "research": _query_research_agent,
    "classification": _query_classification_agent,
    "chat": _query_chat_agent,
}


async def _execute_agent_query(ai_client: Any, agent: str, query: str) -> Dict[str, Any]:
    """Execute agent query with dispatch table (Issue #336 - extracted helper)."""
    handler = AGENT_QUERY_HANDLERS.get(agent)
    if handler:
        return await handler(ai_client, query)
    return {"error": f"Unknown agent: {agent}"}


async def _execute_parallel_agents(ai_client: Any, agents: List[str], query: str) -> Dict[str, Any]:
    """Execute agents in parallel mode (Issue #315: extracted to reduce nesting).

    Args:
        ai_client: AI Stack client instance
        agents: List of agent names to query
        query: Query string

    Returns:
        Dict mapping agent names to their results
    """
    results: Dict[str, Any] = {}
    for agent in agents:
        if agent not in AGENT_QUERY_HANDLERS:
            continue
        try:
            results[agent] = await _execute_agent_query(ai_client, agent, query)
        except Exception:
            results[agent] = {"error": "Internal server error"}
    return results


async def _execute_sequential_agents(ai_client: Any, agents: List[str], query: str) -> Dict[str, Any]:
    """Execute agents sequentially, each building on previous (Issue #315: extracted).

    Args:
        ai_client: AI Stack client instance
        agents: List of agent names to query
        query: Initial query string

    Returns:
        Dict mapping agent names to their results
    """
    results: Dict[str, Any] = {}
    context = query

    for agent in agents:
        try:
            result = await _execute_agent_query(ai_client, agent, context)
            results[agent] = result
            # Update context for next agent
            if result.get("content"):
                context = f"{context}\n\nPrevious result: {result['content']}"
        except Exception:
            results[agent] = {"error": "Internal server error"}

    return results


# ====================================================================
# Multi-Agent Orchestration Endpoints
# ====================================================================


@router.post("/orchestrate/multi-agent-query", response_model=DataResponse[MultiAgentQueryData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="multi_agent_query",
    error_code_prefix="AI_STACK_INTEGRATION",
)
async def multi_agent_query(
    query: str,
    agents: List[str],
    coordination_mode: str = "parallel",
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Orchestrate multiple AI agents for complex query processing.

    Args:
        query: Query to process with multiple agents
        agents: List of agent names to use
        coordination_mode: How to coordinate agents (parallel, sequential)

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()

    # Issue #315: Use extracted helpers to reduce nesting
    if coordination_mode == "parallel":
        results = await _execute_parallel_agents(ai_client, agents, query)
    else:
        results = await _execute_sequential_agents(ai_client, agents, query)

    return create_success_response(
        {
            "query": query,
            "coordination_mode": coordination_mode,
            "agents_used": agents,
            "results": results,
        },
        "Multi-agent query completed successfully",
    )
