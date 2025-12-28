# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Loop Module

Implements the Manus-inspired 6-step agent loop pattern for structured
task execution with event stream integration.

The Agent Loop:
    1. ANALYZE EVENTS    → Understand state from event stream
    2. SELECT TOOLS      → Choose based on plan + knowledge
    3. WAIT FOR EXECUTION → Sandbox executes tool
    4. ITERATE           → One tool per iteration, repeat
    5. SUBMIT RESULTS    → Deliver via message tools
    6. ENTER STANDBY     → Idle state, await new tasks

Usage:
    from src.agent_loop import AgentLoop, AgentLoopConfig

    loop = AgentLoop(
        event_stream=event_manager,
        planner=planner_module,
        tool_executor=parallel_executor,
    )

    # Run a task
    result = await loop.run_task("Implement feature X")
"""

from src.agent_loop.types import (
    LoopState,
    LoopPhase,
    IterationResult,
    AgentLoopConfig,
    ThinkResult,
)
from src.agent_loop.loop import AgentLoop
from src.agent_loop.think_tool import ThinkTool, ThinkCategory

__all__ = [
    # Types
    "LoopState",
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
