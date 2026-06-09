# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Diary API — per-agent cross-session journal access.

Endpoints:
  GET /agent-diary/{agent_name}/entries?last_n=10   — recent entries for one agent
  GET /agent-diary/{agent_name}/search?q=<query>    — semantic search within agent diary
  GET /agent-diary/summary                          — recent entries for all known agents
"""

from typing import List

from fastapi import APIRouter, Depends, Query

from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from memory.agent_diary import AgentDiaryService, list_with_diaries
from utils.response_helpers import create_success_response

router = APIRouter()
logger = get_logger(__name__)

# Canonical list of agent names known to the system (mirrors AGENT_CAPABILITIES in api/agent.py)
_KNOWN_AGENTS: List[str] = [
    "chat",
    "rag",
    "research",
    "web_research_assistant",
    "knowledge_extraction",
    "classification",
    "npu_code_search",
    "development_speedup",
    "system_knowledge_manager",
]


@router.get("/{agent_name}/entries")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_diary_entries",
    error_code_prefix="DIARY",
)
async def get_agent_diary_entries(
    agent_name: str,
    last_n: int = Query(10, ge=1, le=100, description="Number of recent entries"),
    current_user: dict = Depends(get_current_user),
):
    """Return the most recent diary entries for a single agent."""
    diary = AgentDiaryService()
    entries = await diary.read(agent_name, last_n=last_n)
    return create_success_response(
        {
            "agent_name": agent_name,
            "entries": entries,
            "count": len(entries),
        }
    )


@router.get("/{agent_name}/search")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_agent_diary",
    error_code_prefix="DIARY",
)
async def search_agent_diary(
    agent_name: str,
    q: str = Query(..., min_length=1, description="Search query"),
    n: int = Query(5, ge=1, le=50, description="Maximum results"),
    current_user: dict = Depends(get_current_user),
):
    """Semantic search within one agent's diary."""
    diary = AgentDiaryService()
    results = await diary.search(agent_name, query=q, n=n)
    return create_success_response(
        {
            "agent_name": agent_name,
            "query": q,
            "results": results,
            "count": len(results),
        }
    )


@router.get("/summary")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_diary_summary",
    error_code_prefix="DIARY",
)
async def get_agent_diary_summary(
    last_n: int = Query(3, ge=1, le=20, description="Entries per agent"),
    current_user: dict = Depends(get_current_user),
):
    """Return recent diary entries for all known agents (parallel fetch)."""
    summary = await list_with_diaries(_KNOWN_AGENTS, last_n=last_n)
    return create_success_response(
        {
            "agents": summary,
            "total_agents": len(summary),
        }
    )
