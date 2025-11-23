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

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling

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
structured_sessions: Dict[str, List[Dict[str, Any]]] = {}


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: Dict[str, Any]


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


class GenerateSummaryRequest(BaseModel):
    """Request model for generating thinking summary"""

    session_id: Optional[str] = Field("default", description="Session to summarize")


class ClearHistoryRequest(BaseModel):
    """Request model for clearing thinking history"""

    session_id: Optional[str] = Field("default", description="Session to clear")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_structured_thinking_mcp_tools",
    error_code_prefix="STRUCTURED_THINKING_MCP",
)
@router.get("/mcp/tools")
async def get_structured_thinking_mcp_tools() -> List[MCPTool]:
    """Get available MCP tools for structured thinking"""
    tools = [
        MCPTool(
            name="process_thought",
            description=(
                "Record and analyze a thought within a structured cognitive framework. "
                "Organizes thinking through five stages: Problem Definition, Research, Analysis, "
                "Synthesis, and Conclusion. Tracks metadata including tags, axioms used, and "
                "assumptions challenged for comprehensive thought analysis."
            ),
            input_schema={
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
        MCPTool(
            name="generate_summary",
            description=(
                "Generate a structured summary of the entire thinking progression. "
                "Provides overview of thoughts across all cognitive stages, stage distribution, "
                "timeline, tags used, axioms applied, and key insights identified."
            ),
            input_schema={
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
        MCPTool(
            name="clear_history",
            description=(
                "Clear the thinking history for a session, resetting all recorded thoughts. "
                "Useful for starting a new thinking process while preserving other sessions."
            ),
            input_schema={
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
    ]
    return tools


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="process_thought_mcp",
    error_code_prefix="STRUCTURED_THINKING_MCP",
)
@router.post("/mcp/process_thought")
async def process_thought_mcp(request: ProcessThoughtRequest) -> Dict[str, Any]:
    """
    Process and record a thought within the structured cognitive framework

    Tracks thoughts through five stages: Problem Definition, Research, Analysis,
    Synthesis, and Conclusion. Stores metadata for comprehensive analysis.
    """
    session_id = request.session_id or "default"

    # Initialize session if doesn't exist
    if session_id not in structured_sessions:
        structured_sessions[session_id] = []

    # Create thought record
    thought_record = {
        "thought_number": request.thought_number,
        "thought": request.thought,
        "total_thoughts": request.total_thoughts,
        "next_thought_needed": request.next_thought_needed,
        "stage": request.stage.value,
        "tags": request.tags or [],
        "axioms_used": request.axioms_used or [],
        "assumptions_challenged": request.assumptions_challenged or [],
        "timestamp": datetime.now().isoformat(),
    }

    # Store thought
    structured_sessions[session_id].append(thought_record)

    # Calculate stage statistics
    session_thoughts = structured_sessions[session_id]
    stage_counts = {}
    for stage in ThinkingStage:
        stage_counts[stage.value] = sum(
            1 for t in session_thoughts if t["stage"] == stage.value
        )

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
        "current_stage": request.stage.value,
        "thinking_complete": thinking_complete,
        "stage_distribution": stage_counts,
        "session_thought_count": len(session_thoughts),
        "message": f"Processed thought {request.thought_number}/{request.total_thoughts} in {request.stage.value} stage",
    }

    # Identify related thoughts (same tags)
    if request.tags:
        related_thoughts = []
        for idx, t in enumerate(session_thoughts[:-1]):  # Exclude current thought
            if any(tag in t.get("tags", []) for tag in request.tags):
                related_thoughts.append(
                    {
                        "thought_number": t["thought_number"],
                        "stage": t["stage"],
                        "common_tags": [
                            tag for tag in request.tags if tag in t.get("tags", [])
                        ],
                    }
                )

        if related_thoughts:
            response["related_thoughts"] = related_thoughts

    # If thinking is complete, provide completion summary
    if thinking_complete:
        all_tags = set()
        all_axioms = set()
        all_assumptions = set()

        for t in session_thoughts:
            all_tags.update(t.get("tags", []))
            all_axioms.update(t.get("axioms_used", []))
            all_assumptions.update(t.get("assumptions_challenged", []))

        response["completion_summary"] = {
            "total_thoughts": len(session_thoughts),
            "stages_used": [
                stage for stage, count in stage_counts.items() if count > 0
            ],
            "unique_tags": list(all_tags),
            "axioms_applied": list(all_axioms),
            "assumptions_challenged": list(all_assumptions),
        }
        logger.info(
            f"Structured thinking session '{session_id}' completed with {len(session_thoughts)} thoughts"
        )

    return response


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="generate_summary_mcp",
    error_code_prefix="STRUCTURED_THINKING_MCP",
)
@router.post("/mcp/generate_summary")
async def generate_summary_mcp(request: GenerateSummaryRequest) -> Dict[str, Any]:
    """
    Generate a comprehensive summary of the thinking process

    Provides stage distribution, timeline, tags, axioms, and key insights.
    """
    session_id = request.session_id or "default"

    if session_id not in structured_sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    session_thoughts = structured_sessions[session_id]

    if not session_thoughts:
        return {
            "success": True,
            "session_id": session_id,
            "message": "No thoughts recorded in this session",
            "thought_count": 0,
        }

    # Calculate stage distribution
    stage_counts = {}
    stage_thoughts = {}
    for stage in ThinkingStage:
        thoughts_in_stage = [t for t in session_thoughts if t["stage"] == stage.value]
        stage_counts[stage.value] = len(thoughts_in_stage)
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

    # Collect all metadata
    all_tags = set()
    all_axioms = set()
    all_assumptions = set()

    for t in session_thoughts:
        all_tags.update(t.get("tags", []))
        all_axioms.update(t.get("axioms_used", []))
        all_assumptions.update(t.get("assumptions_challenged", []))

    # Build summary
    summary = {
        "success": True,
        "session_id": session_id,
        "overview": {
            "total_thoughts": len(session_thoughts),
            "started_at": session_thoughts[0]["timestamp"],
            "last_thought_at": session_thoughts[-1]["timestamp"],
            "complete": not session_thoughts[-1].get("next_thought_needed", True),
        },
        "stage_distribution": stage_counts,
        "stage_progression": stage_thoughts,
        "metadata_analysis": {
            "unique_tags": list(all_tags),
            "tag_count": len(all_tags),
            "axioms_applied": list(all_axioms),
            "axioms_count": len(all_axioms),
            "assumptions_challenged": list(all_assumptions),
            "assumptions_count": len(all_assumptions),
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

    return summary


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_history_mcp",
    error_code_prefix="STRUCTURED_THINKING_MCP",
)
@router.post("/mcp/clear_history")
async def clear_history_mcp(request: ClearHistoryRequest) -> Dict[str, Any]:
    """Clear the thinking history for a session"""
    session_id = request.session_id or "default"

    if session_id not in structured_sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

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
async def get_structured_session(session_id: str) -> Dict[str, Any]:
    """Get complete structured thinking session"""
    if session_id not in structured_sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    thoughts = structured_sessions[session_id]

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
async def list_structured_sessions() -> Dict[str, Any]:
    """List all active structured thinking sessions"""
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
