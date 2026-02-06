# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Structured Thinking MCP Bridge
Exposes structured thinking capabilities with defined cognitive stages
Based on community MCP implementation (arben-adm/mcp-sequential-thinking)

Provides a structured framework for organizing thoughts through five cognitive stages:
1. Problem Definition - Understanding the problem
2. Research - Gathering relevant information
3. Analysis - Breaking down and examining components
4. Synthesis - Combining insights into solutions
5. Conclusion - Final decisions and recommendations

Enables agents to:
- Organize thoughts through defined cognitive stages
- Track thought progression with metadata
- Generate summaries of thinking processes
- Analyze relationships between thoughts
- Maintain persistent thinking sessions
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.type_defs.common import Metadata
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["structured_thinking_mcp", "mcp"])


class ThinkingStage(str, Enum):
    """Five cognitive stages for structured thinking"""

    PROBLEM_DEFINITION = "Problem Definition"
    RESEARCH = "Research"
    ANALYSIS = "Analysis"
    SYNTHESIS = "Synthesis"
    CONCLUSION = "Conclusion"


# In-memory storage for structured thinking sessions
structured_sessions: Dict[str, List[Metadata]] = {}

# Lock for thread-safe access to structured_sessions
_structured_sessions_lock = asyncio.Lock()


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: Metadata


class ProcessThoughtRequest(BaseModel):
    """Request model for processing a thought in structured framework"""

    thought: str = Field(..., description="The content of the thought")
    thought_number: int = Field(
        ..., ge=1, description="Position in the thinking sequence"
    )
    total_thoughts: int = Field(
        ..., ge=1, description="Expected total number of thoughts"
    )
    next_thought_needed: bool = Field(
        ..., description="Whether more thoughts will follow"
    )
    stage: ThinkingStage = Field(..., description="Cognitive stage for this thought")

    # Optional metadata
    tags: Optional[List[str]] = Field(
        None, description="Keywords or categories for this thought"
    )
    axioms_used: Optional[List[str]] = Field(
        None, description="Fundamental principles applied"
    )
    assumptions_challenged: Optional[List[str]] = Field(
        None, description="Assumptions being questioned"
    )

    # Session management
    session_id: Optional[str] = Field(
        "default", description="Thinking session identifier"
    )

    # === Issue #372: Feature Envy Reduction Methods ===

    def to_thought_record(self) -> Metadata:
        """Convert request to thought record for storage (Issue #372 - reduces feature envy)."""
        return {
            "thought_number": self.thought_number,
            "thought": self.thought,
            "total_thoughts": self.total_thoughts,
            "next_thought_needed": self.next_thought_needed,
            "stage": self.stage.value,
            "tags": self.tags or [],
            "axioms_used": self.axioms_used or [],
            "assumptions_challenged": self.assumptions_challenged or [],
            "timestamp": datetime.now().isoformat(),
        }

    def get_progress_percentage(self) -> float:
        """Calculate progress percentage (Issue #372 - reduces feature envy)."""
        return (self.thought_number / self.total_thoughts) * 100

    def get_session_key(self) -> str:
        """Get session key with fallback (Issue #372 - reduces feature envy)."""
        return self.session_id or "default"

    def is_thinking_complete(self) -> bool:
        """Check if thinking process is complete (Issue #372 - reduces feature envy)."""
        return not self.next_thought_needed

    def get_progress_message(self) -> str:
        """Get formatted progress message (Issue #372 - reduces feature envy)."""
        return (
            f"Processed thought {self.thought_number}/{self.total_thoughts} "
            f"in {self.stage.value} stage"
        )


class GenerateSummaryRequest(BaseModel):
    """Request model for generating thinking summary"""

    session_id: Optional[str] = Field("default", description="Session to summarize")


class ClearHistoryRequest(BaseModel):
    """Request model for clearing thinking history"""

    session_id: Optional[str] = Field("default", description="Session to clear")


# =============================================================================
# Helper Functions (Issue #665)
# =============================================================================


def _calculate_stage_distribution(session_thoughts: List[Metadata]) -> Dict[str, int]:
    """Calculate the distribution of thoughts across cognitive stages (Issue #665: extracted helper)."""
    stage_counts = {}
    for stage in ThinkingStage:
        stage_counts[stage.value] = sum(
            1 for t in session_thoughts if t["stage"] == stage.value
        )
    return stage_counts


def _collect_thought_metadata(session_thoughts: List[Metadata]) -> Dict[str, set]:
    """Collect all metadata (tags, axioms, assumptions) from thoughts (Issue #665: extracted helper)."""
    all_tags = set()
    all_axioms = set()
    all_assumptions = set()

    for t in session_thoughts:
        all_tags.update(t.get("tags", []))
        all_axioms.update(t.get("axioms_used", []))
        all_assumptions.update(t.get("assumptions_challenged", []))

    return {
        "tags": all_tags,
        "axioms": all_axioms,
        "assumptions": all_assumptions,
    }


def _find_related_thoughts(
    request_tags: List[str], session_thoughts: List[Metadata]
) -> List[Metadata]:
    """Find thoughts with matching tags (Issue #665: extracted helper)."""
    related_thoughts = []
    for t in session_thoughts[:-1]:  # Exclude current thought
        if any(tag in t.get("tags", []) for tag in request_tags):
            related_thoughts.append(
                {
                    "thought_number": t["thought_number"],
                    "stage": t["stage"],
                    "common_tags": [
                        tag for tag in request_tags if tag in t.get("tags", [])
                    ],
                }
            )
    return related_thoughts


def _build_completion_summary(
    session_thoughts: List[Metadata], stage_counts: Dict[str, int]
) -> Metadata:
    """Build completion summary when thinking is complete (Issue #665: extracted helper)."""
    metadata = _collect_thought_metadata(session_thoughts)
    return {
        "total_thoughts": len(session_thoughts),
        "stages_used": [stage for stage, count in stage_counts.items() if count > 0],
        "unique_tags": list(metadata["tags"]),
        "axioms_applied": list(metadata["axioms"]),
        "assumptions_challenged": list(metadata["assumptions"]),
    }


def _build_stage_progression(
    session_thoughts: List[Metadata],
) -> Dict[str, List[Metadata]]:
    """Build stage progression with summarized thoughts (Issue #665: extracted helper)."""
    stage_thoughts = {}
    for stage in ThinkingStage:
        thoughts_in_stage = [t for t in session_thoughts if t["stage"] == stage.value]
        if thoughts_in_stage:
            stage_thoughts[stage.value] = [
                {
                    "thought_number": t["thought_number"],
                    "thought": (
                        t["thought"][:100] + "..."
                        if len(t["thought"]) > 100
                        else t["thought"]
                    ),
                }
                for t in thoughts_in_stage
            ]
    return stage_thoughts


# Issue #281: MCP tool definitions extracted from get_structured_thinking_mcp_tools
STRUCTURED_THINKING_MCP_TOOL_DEFINITIONS = (
    (
        "process_thought",
        "Record and analyze a thought within a structured cognitive framework. "
        "Organizes thinking through five stages: Problem Definition, Research, Analysis, "
        "Synthesis, and Conclusion. Tracks metadata including tags, axioms used, and "
        "assumptions challenged for comprehensive thought analysis.",
        {
            "type": "object",
            "properties": {
                "thought": {
                    "type": "string",
                    "description": "The content of the thought to record",
                },
                "thought_number": {
                    "type": "integer",
                    "description": "Position in the thinking sequence",
                    "minimum": 1,
                },
                "total_thoughts": {
                    "type": "integer",
                    "description": "Expected total number of thoughts",
                    "minimum": 1,
                },
                "next_thought_needed": {
                    "type": "boolean",
                    "description": "Whether more thoughts will follow this one",
                },
                "stage": {
                    "type": "string",
                    "enum": [
                        "Problem Definition",
                        "Research",
                        "Analysis",
                        "Synthesis",
                        "Conclusion",
                    ],
                    "description": "Cognitive stage for this thought",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords or categories for this thought",
                },
                "axioms_used": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fundamental principles or axioms applied",
                },
                "assumptions_challenged": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Assumptions being questioned or challenged",
                },
                "session_id": {
                    "type": "string",
                    "description": "Thinking session identifier",
                    "default": "default",
                },
            },
            "required": [
                "thought",
                "thought_number",
                "total_thoughts",
                "next_thought_needed",
                "stage",
            ],
        },
    ),
    (
        "generate_summary",
        "Generate a structured summary of the entire thinking progression. "
        "Provides overview of thoughts across all cognitive stages, stage distribution, "
        "timeline, tags used, axioms applied, and key insights identified.",
        {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session to summarize",
                    "default": "default",
                }
            },
        },
    ),
    (
        "clear_history",
        "Clear the thinking history for a session, resetting all recorded thoughts. "
        "Useful for starting a new thinking process while preserving other sessions.",
        {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session to clear",
                    "default": "default",
                }
            },
        },
    ),
)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_structured_thinking_mcp_tools",
    error_code_prefix="STRUCTURED_THINKING_MCP",
)
@router.get("/mcp/tools")
async def get_structured_thinking_mcp_tools() -> List[MCPTool]:
    """
    Get available MCP tools for structured thinking.

    Issue #281: Refactored to use module-level STRUCTURED_THINKING_MCP_TOOL_DEFINITIONS.
    Reduced from 110 lines to ~10 lines.
    """
    # Issue #281: Build MCPTool instances from module-level definitions
    return [
        MCPTool(name=name, description=desc, input_schema=schema)
        for name, desc, schema in STRUCTURED_THINKING_MCP_TOOL_DEFINITIONS
    ]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="process_thought_mcp",
    error_code_prefix="STRUCTURED_THINKING_MCP",
)
@router.post("/mcp/process_thought")
async def process_thought_mcp(request: ProcessThoughtRequest) -> Metadata:
    """
    Process and record a thought within the structured cognitive framework.

    Issue #665: Refactored to use extracted helpers for stage distribution,
    related thoughts, and completion summary.

    Tracks thoughts through five stages: Problem Definition, Research, Analysis,
    Synthesis, and Conclusion. Stores metadata for comprehensive analysis.
    """
    # Issue #372: Use model methods instead of direct attribute access
    session_id = request.get_session_key()

    async with _structured_sessions_lock:
        if session_id not in structured_sessions:
            structured_sessions[session_id] = []

    # Issue #372: Use model method for thought record creation
    thought_record = request.to_thought_record()

    # Store thought (thread-safe)
    async with _structured_sessions_lock:
        structured_sessions[session_id].append(thought_record)
        session_thoughts = list(structured_sessions[session_id])

    # Issue #665: Use extracted helper for stage distribution
    stage_counts = _calculate_stage_distribution(session_thoughts)

    # Issue #372: Use model methods for computed values
    thinking_complete = request.is_thinking_complete()

    # Build response
    response = {
        "success": True,
        "session_id": session_id,
        "thought_number": request.thought_number,
        "total_thoughts": request.total_thoughts,
        "progress_percentage": round(request.get_progress_percentage(), 1),
        "current_stage": request.stage.value,
        "thinking_complete": thinking_complete,
        "stage_distribution": stage_counts,
        "session_thought_count": len(session_thoughts),
        "message": request.get_progress_message(),
    }

    # Issue #665: Use extracted helper for related thoughts
    if request.tags:
        related_thoughts = _find_related_thoughts(request.tags, session_thoughts)
        if related_thoughts:
            response["related_thoughts"] = related_thoughts

    # Issue #665: Use extracted helper for completion summary
    if thinking_complete:
        response["completion_summary"] = _build_completion_summary(
            session_thoughts, stage_counts
        )
        logger.info(
            "Structured thinking session '%s' completed with %d thoughts",
            session_id,
            len(session_thoughts),
        )

    return response


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="generate_summary_mcp",
    error_code_prefix="STRUCTURED_THINKING_MCP",
)
@router.post("/mcp/generate_summary")
async def generate_summary_mcp(request: GenerateSummaryRequest) -> Metadata:
    """
    Generate a comprehensive summary of the thinking process.

    Issue #665: Refactored to use extracted helpers for stage distribution,
    stage progression, and metadata collection.

    Provides stage distribution, timeline, tags, axioms, and key insights.
    """
    session_id = request.session_id or "default"

    async with _structured_sessions_lock:
        if session_id not in structured_sessions:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )
        session_thoughts = list(structured_sessions[session_id])

    if not session_thoughts:
        return {
            "success": True,
            "session_id": session_id,
            "message": "No thoughts recorded in this session",
            "thought_count": 0,
        }

    # Issue #665: Use extracted helpers
    stage_counts = _calculate_stage_distribution(session_thoughts)
    stage_progression = _build_stage_progression(session_thoughts)
    metadata = _collect_thought_metadata(session_thoughts)

    return {
        "success": True,
        "session_id": session_id,
        "overview": {
            "total_thoughts": len(session_thoughts),
            "started_at": session_thoughts[0]["timestamp"],
            "last_thought_at": session_thoughts[-1]["timestamp"],
            "complete": not session_thoughts[-1].get("next_thought_needed", True),
        },
        "stage_distribution": stage_counts,
        "stage_progression": stage_progression,
        "metadata_analysis": {
            "unique_tags": list(metadata["tags"]),
            "tag_count": len(metadata["tags"]),
            "axioms_applied": list(metadata["axioms"]),
            "axioms_count": len(metadata["axioms"]),
            "assumptions_challenged": list(metadata["assumptions"]),
            "assumptions_count": len(metadata["assumptions"]),
        },
        "cognitive_flow": [
            {
                "thought_number": t["thought_number"],
                "stage": t["stage"],
                "timestamp": t["timestamp"],
            }
            for t in session_thoughts
        ],
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_history_mcp",
    error_code_prefix="STRUCTURED_THINKING_MCP",
)
@router.post("/mcp/clear_history")
async def clear_history_mcp(request: ClearHistoryRequest) -> Metadata:
    """Clear the thinking history for a session"""
    session_id = request.session_id or "default"

    async with _structured_sessions_lock:
        if session_id not in structured_sessions:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )

        thought_count = len(structured_sessions[session_id])
        del structured_sessions[session_id]

    return {
        "success": True,
        "session_id": session_id,
        "thoughts_cleared": thought_count,
        "message": f"Cleared {thought_count} thoughts from session '{session_id}'",
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_structured_session",
    error_code_prefix="STRUCTURED_THINKING_MCP",
)
@router.get("/sessions/{session_id}")
async def get_structured_session(session_id: str) -> Metadata:
    """Get complete structured thinking session"""
    async with _structured_sessions_lock:
        if session_id not in structured_sessions:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )

        # Create a copy of thoughts for processing outside the lock
        thoughts = list(structured_sessions[session_id])

    # Stage analysis
    stage_analysis = {}
    for stage in ThinkingStage:
        stage_thoughts = [t for t in thoughts if t["stage"] == stage.value]
        stage_analysis[stage.value] = {
            "count": len(stage_thoughts),
            "thoughts": stage_thoughts,
        }

    return {
        "session_id": session_id,
        "thought_count": len(thoughts),
        "thoughts": thoughts,
        "stage_analysis": stage_analysis,
        "started_at": thoughts[0]["timestamp"] if thoughts else None,
        "last_thought_at": thoughts[-1]["timestamp"] if thoughts else None,
        "complete": (
            not thoughts[-1].get("next_thought_needed", True) if thoughts else False
        ),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_structured_sessions",
    error_code_prefix="STRUCTURED_THINKING_MCP",
)
@router.get("/sessions")
async def list_structured_sessions() -> Metadata:
    """List all active structured thinking sessions"""
    async with _structured_sessions_lock:
        sessions = []
        for session_id, thoughts in structured_sessions.items():
            # Calculate stage distribution
            stage_counts = {}
            for stage in ThinkingStage:
                stage_counts[stage.value] = sum(
                    1 for t in thoughts if t["stage"] == stage.value
                )

            sessions.append(
                {
                    "session_id": session_id,
                    "thought_count": len(thoughts),
                    "stage_distribution": stage_counts,
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
