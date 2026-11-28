# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Loop Module

Implements the Manus-inspired 6-step agent loop pattern for structured
task execution with event stream integration.

PORTED TO THE CHAT GRAPH (maintainer decision 2026-11-07, #20846): the chat graph
(``chat_workflow/graph.py``) is the canonical loop. The planner and stall
escalation are ported as graph nodes (#21023, #21022). ``AgentLoop`` is never
instantiated in production; whether to retire it is #21025.

The Agent Loop:
    1. ANALYZE EVENTS    → Understand state from event stream
    2. SELECT TOOLS      → Choose based on plan + knowledge
    3. WAIT FOR EXECUTION → Sandbox executes tool
    4. ITERATE           → One tool per iteration, repeat
    5. SUBMIT RESULTS    → Deliver via message tools
    6. ENTER STANDBY     → Idle state, await new tasks

Usage:
    from agent_loop import AgentLoop, AgentLoopConfig

    loop = AgentLoop(
        event_stream=event_manager,
        planner=planner_module,
        tool_executor=parallel_executor,
    )

    # Run a task
    result = await loop.run_task("Implement feature X")
"""

from agent_loop.loop import AgentLoop
from agent_loop.think_tool import ThinkCategory, ThinkTool
from agent_loop.types import (
    AgentLoopConfig,
    IterationResult,
    LoopOutcome,
    LoopPhase,
    LoopState,
    ThinkResult,
)

__all__ = [
    # Types
    "LoopState",
    "LoopOutcome",
    "LoopPhase",
    "IterationResult",
    "AgentLoopConfig",
    "ThinkResult",
    # Loop
    "AgentLoop",
    # Think Tool
    "ThinkTool",
    "ThinkCategory",
]
