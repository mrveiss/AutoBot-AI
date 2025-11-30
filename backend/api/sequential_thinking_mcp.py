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

import logging
from datetime import datetime
from typing import Dict, List, Optional

from backend.type_defs.common import Metadata
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sequential_thinking_mcp", "mcp"])

# In-memory storage for thinking sessions (could be moved to Redis for persistence)
thinking_sessions: Dict[str, List[Metadata]] = {}

# Lock for thread-safe access to thinking_sessions
_thinking_sessions_lock = asyncio.Lock()


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: Metadata


class SequentialThinkingRequest(BaseModel):
    """Request model for sequential thinking tool"""

    thought: str = Field(..., description="Current thinking step and analysis")
    thought_number: int = Field(
        ..., ge=1, description="Current thought number in sequence"
    )
    total_thoughts: int = Field(
        ..., ge=1, description="Estimated total thoughts needed"
    )
    next_thought_needed: bool = Field(
        ..., description="Whether another thought step is needed"
    )

    # Optional revision/branching parameters
    is_revision: Optional[bool] = Field(
        False, description="Whether this revises previous thinking"
    )
    revises_thought: Optional[int] = Field(
        None, ge=1, description="Which thought is being reconsidered"
    )
    branch_from_thought: Optional[int] = Field(
        None, ge=1, description="Branching point thought number"
    )
    branch_id: Optional[str] = Field(None, description="Branch identifier")
    needs_more_thoughts: Optional[bool] = Field(
        False, description="If more thoughts are needed beyond initial estimate"
    )

    # Session management
    session_id: Optional[str] = Field(
        "default", description="Thinking session identifier"
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_sequential_thinking_mcp_tools",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
@router.get("/mcp/tools")
async def get_sequential_thinking_mcp_tools() -> List[MCPTool]:
    """Get available MCP tools for sequential thinking"""
    tools = [
        MCPTool(
            name="sequential_thinking",
            description=(
                "A tool for dynamic and reflective problem-solving through a structured thinking process. "
                "Enables breaking down complex problems into steps, revising thoughts as understanding deepens, "
                "and branching into alternative reasoning paths. Adjusts total thoughts dynamically and "
                "generates/verifies solution hypotheses."
            ),
            input_schema={
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
                        "description": (
                            "Estimated total thoughts needed (can be adjusted)"
                        ),
                        "minimum": 1,
                    },
                    "next_thought_needed": {
                        "type": "boolean",
                        "description": (
                            "Whether another thought step is needed after this one"
                        ),
                    },
                    "is_revision": {
                        "type": "boolean",
                        "description": "Whether this thought revises previous thinking",
                        "default": False,
                    },
                    "revises_thought": {
                        "type": "integer",
                        "description": (
                            "Which thought number is being reconsidered (if is_revision is true)"
                        ),
                        "minimum": 1,
                    },
                    "branch_from_thought": {
                        "type": "integer",
                        "description": (
                            "Thought number to branch from (for alternative reasoning paths)"
                        ),
                        "minimum": 1,
                    },
                    "branch_id": {
                        "type": "string",
                        "description": "Identifier for the current reasoning branch",
                    },
                    "needs_more_thoughts": {
                        "type": "boolean",
                        "description": (
                            "If more thoughts are needed beyond initial estimate"
                        ),
                        "default": False,
                    },
                    "session_id": {
                        "type": "string",
                        "description": (
                            "Thinking session identifier for tracking multiple sessions"
                        ),
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
    ]
    return tools


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sequential_thinking_mcp",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
@router.post("/mcp/sequential_thinking")
async def sequential_thinking_mcp(request: SequentialThinkingRequest) -> Metadata:
    """
    Execute sequential thinking tool

    Stores and tracks thinking progression through a problem-solving process.
    Supports revision, branching, and dynamic adjustment of thought count.
    """
    session_id = request.session_id or "default"

    async with _thinking_sessions_lock:
        # Initialize session if doesn't exist
        if session_id not in thinking_sessions:
            thinking_sessions[session_id] = []

    # Validate thought progression
    if (
        request.thought_number > request.total_thoughts
        and not request.needs_more_thoughts
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Thought number {request.thought_number} exceeds total thoughts"
                f"{request.total_thoughts}. Set needs_more_thoughts=true to extend."
            )
        )

    # Create thought record
    thought_record = {
        "thought_number": request.thought_number,
        "thought": request.thought,
        "total_thoughts": request.total_thoughts,
        "next_thought_needed": request.next_thought_needed,
        "is_revision": request.is_revision,
        "revises_thought": request.revises_thought,
        "branch_from_thought": request.branch_from_thought,
        "branch_id": request.branch_id,
        "needs_more_thoughts": request.needs_more_thoughts,
        "timestamp": datetime.now().isoformat(),
    }

    # Handle revision
    if request.is_revision and request.revises_thought:
        thought_record["revision_of"] = request.revises_thought
        logger.info(
            f"Thought {request.thought_number} revises thought {request.revises_thought}"
        )

    # Handle branching
    if request.branch_from_thought:
        thought_record["branched_from"] = request.branch_from_thought
        logger.info(
            f"Thought {request.thought_number} branches from thought {request.branch_from_thought} (branch: {request.branch_id})"
        )

    # Store thought (thread-safe)
    async with _thinking_sessions_lock:
        thinking_sessions[session_id].append(thought_record)
        session_thought_count = len(thinking_sessions[session_id])

    # Calculate progress
    progress_percentage = (request.thought_number / request.total_thoughts) * 100

    # Determine if thinking is complete
    thinking_complete = not request.next_thought_needed

    # Build response
    response = {
        "success": True,
        "session_id": session_id,
        "thought_number": request.thought_number,
        "total_thoughts": request.total_thoughts,
        "progress_percentage": round(progress_percentage, 1),
        "thinking_complete": thinking_complete,
        "session_thought_count": session_thought_count,
        "message": (
            f"Recorded thought {request.thought_number}/{request.total_thoughts}"
        ),
    }

    # Add revision info
    if request.is_revision:
        response["revision_info"] = {
            "is_revision": True,
            "revises_thought": request.revises_thought,
        }

    # Add branch info
    if request.branch_from_thought:
        response["branch_info"] = {
            "branched": True,
            "branch_from_thought": request.branch_from_thought,
            "branch_id": request.branch_id,
        }

    # If thinking is complete, provide summary
    if thinking_complete:
        response["summary"] = {
            "total_thoughts_recorded": len(thinking_sessions[session_id]),
            "revisions_made": sum(
                1 for t in thinking_sessions[session_id] if t.get("is_revision")
            ),
            "branches_created": len(
                set(
                    t.get("branch_id")
                    for t in thinking_sessions[session_id]
                    if t.get("branch_id")
                )
            ),
            "thinking_duration_thoughts": request.thought_number,
        }
        logger.info(
            f"Sequential thinking session '{session_id}' completed with {request.thought_number} thoughts"
        )

    return response


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_thinking_session",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
@router.get("/sessions/{session_id}")
async def get_thinking_session(session_id: str) -> Metadata:
    """Get complete thinking session history"""
    if session_id not in thinking_sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    thoughts = thinking_sessions[session_id]

    return {
        "session_id": session_id,
        "thought_count": len(thoughts),
        "thoughts": thoughts,
        "revisions": [t for t in thoughts if t.get("is_revision")],
        "branches": list(
            set(t.get("branch_id") for t in thoughts if t.get("branch_id"))
        ),
        "started_at": thoughts[0]["timestamp"] if thoughts else None,
        "last_thought_at": thoughts[-1]["timestamp"] if thoughts else None,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_thinking_session",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
@router.delete("/sessions/{session_id}")
async def clear_thinking_session(session_id: str) -> Metadata:
    """Clear a thinking session"""
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_thinking_sessions",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
@router.get("/sessions")
async def list_thinking_sessions() -> Metadata:
    """List all active thinking sessions"""
    sessions = []
    for session_id, thoughts in thinking_sessions.items():
        sessions.append(
            {
                "session_id": session_id,
                "thought_count": len(thoughts),
                "started_at": thoughts[0]["timestamp"] if thoughts else None,
                "last_thought_at": thoughts[-1]["timestamp"] if thoughts else None,
                "complete": (
                    not thoughts[-1].get("next_thought_needed", True)
                    if thoughts
                    else False
                ),
            }
        )

    return {"session_count": len(sessions), "sessions": sessions}
