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
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.type_defs.common import Metadata
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sequential_thinking_mcp", "mcp"])

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

    def to_thought_record(self) -> Metadata:
        """Convert to thought record for storage (Issue #372 - reduces feature envy).

        Returns:
            Dictionary containing thought record fields.
        """
        return {
            "thought_number": self.thought_number,
            "thought": self.thought,
            "total_thoughts": self.total_thoughts,
            "next_thought_needed": self.next_thought_needed,
            "is_revision": self.is_revision,
            "revises_thought": self.revises_thought,
            "branch_from_thought": self.branch_from_thought,
            "branch_id": self.branch_id,
            "needs_more_thoughts": self.needs_more_thoughts,
            "timestamp": datetime.now().isoformat(),
        }

    def get_progress_percentage(self) -> float:
        """Calculate progress percentage (Issue #372 - reduces feature envy)."""
        return (self.thought_number / self.total_thoughts) * 100

    def get_session_key(self) -> str:
        """Get session key with fallback (Issue #372 - reduces feature envy)."""
        return self.session_id or "default"

    def is_valid_thought_number(self) -> bool:
        """Check if thought number is valid (Issue #372 - reduces feature envy)."""
        return self.thought_number <= self.total_thoughts or self.needs_more_thoughts

    def has_revision(self) -> bool:
        """Check if this is a revision (Issue #372 - reduces feature envy)."""
        return bool(self.is_revision)

    def get_revision_info(self) -> Optional[Metadata]:
        """Get revision info dict if this is a revision (Issue #372 - reduces feature envy)."""
        if not self.is_revision:
            return None
        return {
            "is_revision": True,
            "revises_thought": self.revises_thought,
        }

    def has_branch(self) -> bool:
        """Check if this is a branch (Issue #372 - reduces feature envy)."""
        return bool(self.branch_from_thought)

    def get_branch_info(self) -> Optional[Metadata]:
        """Get branch info dict if this is a branch (Issue #372 - reduces feature envy)."""
        if not self.branch_from_thought:
            return None
        return {
            "branched": True,
            "branch_from_thought": self.branch_from_thought,
            "branch_id": self.branch_id,
        }

    def get_progress_message(self) -> str:
        """Get progress message string (Issue #372 - reduces feature envy)."""
        return f"Recorded thought {self.thought_number}/{self.total_thoughts}"


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_sequential_thinking_mcp_tools",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
@router.get("/mcp/tools")
async def get_sequential_thinking_mcp_tools() -> List[MCPTool]:
    """
    Get available MCP tools for sequential thinking.

    Issue #281: Refactored to use module-level SEQUENTIAL_THINKING_MCP_TOOL_DEFINITION.
    Reduced from 84 lines to ~10 lines (88% reduction).
    """
    name, description, input_schema = SEQUENTIAL_THINKING_MCP_TOOL_DEFINITION
    return [MCPTool(name=name, description=description, input_schema=input_schema)]


def _enrich_thought_record(
    thought_record: dict, request: SequentialThinkingRequest
) -> None:
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
        "branches_created": len(
            set(t.get("branch_id") for t in session_thoughts if t.get("branch_id"))
        ),
        "thinking_duration_thoughts": thought_number,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sequential_thinking_mcp",
    error_code_prefix="SEQUENTIAL_THINKING_MCP",
)
@router.post("/mcp/sequential_thinking")
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
            response["summary"] = _calculate_session_summary(
                thinking_sessions[session_id], request.thought_number
            )
        logger.info(
            "Sequential thinking session '%s' completed with %s thoughts",
            session_id,
            request.thought_number,
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
    async with _thinking_sessions_lock:
        if session_id not in thinking_sessions:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )

        # Create a copy under lock to prevent race conditions
        thoughts = list(thinking_sessions[session_id])

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
    async with _thinking_sessions_lock:
        if session_id not in thinking_sessions:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )

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
    async with _thinking_sessions_lock:
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
