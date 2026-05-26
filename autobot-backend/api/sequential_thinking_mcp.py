# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Sequential Thinking MCP Bridge
Exposes sequential thinking capabilities as MCP tools for LLM agents
Based on official Anthropic MCP implementation

Provides dynamic, reflective problem-solving through structured thinking process.
Enables agents to:
- Break down complex problems into manageable steps
- Revise and refine thoughts as understanding deepens
- Branch into alternative paths of reasoning
- Generate and verify solution hypotheses
"""

import asyncio
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from services.mcp_bridge_manifest import MCPBridgeManifest

from api.schemas_common import DataResponse

MANIFEST = MCPBridgeManifest(
    name="sequential_thinking_mcp",
    version="1.0.0",
    description="Sequential Thinking - Dynamic Problem-Solving Framework",
    features=["sequential_thinking", "thought_tracking", "branching", "revision"],
    endpoint="/api/sequential_thinking/mcp/tools",
)
from api.schemas_workflows import (
    SequentialThinkingClearData,
    SequentialThinkingMCPTool,
    SequentialThinkingMCPToolsResponse,
    SequentialThinkingRequest,
    SequentialThinkingResponse,
    SequentialThinkingSessionListResponse,
    SequentialThinkingSessionResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from type_defs.common import Metadata

logger = get_logger(__name__)
router = APIRouter(
    tags=["sequential_thinking_mcp", "mcp"],
    dependencies=[Depends(check_admin_permission)],
)

# In-memory storage for thinking sessions (could be moved to Redis for persistence)
thinking_sessions: Dict[str, List[Metadata]] = {}

# Lock for thread-safe access to thinking_sessions
_thinking_sessions_lock = asyncio.Lock()

# Issue #281: MCP tool definition extracted from get_sequential_thinking_mcp_tools
# Tuple of (name, description, input_schema) for sequential thinking tool
SEQUENTIAL_THINKING_MCP_TOOL_DEFINITION = (
    "sequential_thinking",
    (
        "A tool for dynamic and reflective problem-solving through a structured thinking process. "
        "Enables breaking down complex problems into steps, revising thoughts as understanding deepens, "
        "and branching into alternative reasoning paths. Adjusts total thoughts dynamically and "
        "generates/verifies solution hypotheses."
    ),
    {
        "type": "object",
        "properties": {
            "thought": {
                "type": "string",
                "description": "Your current thinking step and analysis",
            },
            "thought_number": {
                "type": "integer",
                "description": "Current thought number in the sequence",
                "minimum": 1,
            },
            "total_thoughts": {
                "type": "integer",
                "description": "Estimated total thoughts needed (can be adjusted)",
                "minimum": 1,
            },
            "next_thought_needed": {
                "type": "boolean",
                "description": "Whether another thought step is needed after this one",
            },
            "is_revision": {
                "type": "boolean",
                "description": "Whether this thought revises previous thinking",
                "default": False,
            },
            "revises_thought": {
                "type": "integer",
                "description": "Which thought number is being reconsidered (if is_revision is true)",
                "minimum": 1,
            },
            "branch_from_thought": {
                "type": "integer",
                "description": "Thought number to branch from (for alternative reasoning paths)",
                "minimum": 1,
            },
            "branch_id": {
                "type": "string",
                "description": "Identifier for the current reasoning branch",
            },
            "needs_more_thoughts": {
                "type": "boolean",
                "description": "If more thoughts are needed beyond initial estimate",
                "default": False,
            },
            "session_id": {
                "type": "string",
                "description": "Thinking session identifier for tracking multiple sessions",
                "default": "default",
            },
        },
        "required": [
            "thought",
            "thought_number",
            "total_thoughts",
            "next_thought_needed",
        ],
    },
)


@router.get("/mcp/tools", response_model=SequentialThinkingMCPToolsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_sequential_thinking_mcp_tools",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
async def get_sequential_thinking_mcp_tools() -> List[SequentialThinkingMCPTool]:
    """
    Get available MCP tools for sequential thinking.

    Issue #281: Refactored to use module-level SEQUENTIAL_THINKING_MCP_TOOL_DEFINITION.
    Reduced from 84 lines to ~10 lines (88% reduction).
    """
    name, description, input_schema = SEQUENTIAL_THINKING_MCP_TOOL_DEFINITION
    return [SequentialThinkingMCPTool(name=name, description=description, input_schema=input_schema)]


def _enrich_thought_record(thought_record: dict, request: SequentialThinkingRequest) -> None:
    """Add revision/branch info to thought record (Issue #398: extracted)."""
    if request.is_revision and request.revises_thought:
        thought_record["revision_of"] = request.revises_thought
        logger.info(
            "Thought %s revises thought %s",
            request.thought_number,
            request.revises_thought,
        )

    if request.branch_from_thought:
        thought_record["branched_from"] = request.branch_from_thought
        logger.info(
            "Thought %d branches from thought %d (branch: %s)",
            request.thought_number,
            request.branch_from_thought,
            request.branch_id,
        )


def _calculate_session_summary(session_thoughts: list, thought_number: int) -> dict:
    """Calculate summary for completed thinking session (Issue #398: extracted)."""
    return {
        "total_thoughts_recorded": len(session_thoughts),
        "revisions_made": sum(1 for t in session_thoughts if t.get("is_revision")),
        "branches_created": len(set(t.get("branch_id") for t in session_thoughts if t.get("branch_id"))),
        "thinking_duration_thoughts": thought_number,
    }


@router.post("/mcp/sequential_thinking", response_model=SequentialThinkingResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sequential_thinking_mcp",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
async def sequential_thinking_mcp(request: SequentialThinkingRequest) -> Metadata:
    """Execute sequential thinking tool (Issue #398: refactored)."""
    session_id = request.get_session_key()

    async with _thinking_sessions_lock:
        if session_id not in thinking_sessions:
            thinking_sessions[session_id] = []

    if not request.is_valid_thought_number():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Thought number {request.thought_number} exceeds total thoughts "
                f"{request.total_thoughts}. Set needs_more_thoughts=true to extend."
            ),
        )

    thought_record = request.to_thought_record()
    _enrich_thought_record(thought_record, request)

    async with _thinking_sessions_lock:
        thinking_sessions[session_id].append(thought_record)
        session_thought_count = len(thinking_sessions[session_id])

    thinking_complete = not request.next_thought_needed

    response = {
        "success": True,
        "session_id": session_id,
        "thought_number": request.thought_number,
        "total_thoughts": request.total_thoughts,
        "progress_percentage": round(request.get_progress_percentage(), 1),
        "thinking_complete": thinking_complete,
        "session_thought_count": session_thought_count,
        "message": request.get_progress_message(),
    }

    if revision_info := request.get_revision_info():
        response["revision_info"] = revision_info
    if branch_info := request.get_branch_info():
        response["branch_info"] = branch_info

    if thinking_complete:
        async with _thinking_sessions_lock:
            response["summary"] = _calculate_session_summary(thinking_sessions[session_id], request.thought_number)
        logger.info(
            "Sequential thinking session '%s' completed with %s thoughts",
            session_id,
            request.thought_number,
        )

    return response


@router.get("/sessions/{session_id}", response_model=SequentialThinkingSessionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_thinking_session",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
async def get_thinking_session(session_id: str) -> Metadata:
    """Get complete thinking session history"""
    async with _thinking_sessions_lock:
        if session_id not in thinking_sessions:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

        # Create a copy under lock to prevent race conditions
        thoughts = list(thinking_sessions[session_id])

    return {
        "session_id": session_id,
        "thought_count": len(thoughts),
        "thoughts": thoughts,
        "revisions": [t for t in thoughts if t.get("is_revision")],
        "branches": list(set(t.get("branch_id") for t in thoughts if t.get("branch_id"))),
        "started_at": thoughts[0]["timestamp"] if thoughts else None,
        "last_thought_at": thoughts[-1]["timestamp"] if thoughts else None,
    }


@router.delete("/sessions/{session_id}", response_model=DataResponse[SequentialThinkingClearData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_thinking_session",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
async def clear_thinking_session(session_id: str) -> Metadata:
    """Clear a thinking session"""
    async with _thinking_sessions_lock:
        if session_id not in thinking_sessions:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

        thought_count = len(thinking_sessions[session_id])
        del thinking_sessions[session_id]

    return {
        "success": True,
        "session_id": session_id,
        "thoughts_cleared": thought_count,
        "message": f"Cleared thinking session '{session_id}'",
    }


@router.get("/sessions", response_model=SequentialThinkingSessionListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_thinking_sessions",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
async def list_thinking_sessions() -> Metadata:
    """List all active thinking sessions"""
    async with _thinking_sessions_lock:
        sessions = []
        for session_id, thoughts in thinking_sessions.items():
            sessions.append(
                {
                    "session_id": session_id,
                    "thought_count": len(thoughts),
                    "started_at": thoughts[0]["timestamp"] if thoughts else None,
                    "last_thought_at": thoughts[-1]["timestamp"] if thoughts else None,
                    "complete": (not thoughts[-1].get("next_thought_needed", True) if thoughts else False),
                }
            )

    return {"session_count": len(sessions), "sessions": sessions}
