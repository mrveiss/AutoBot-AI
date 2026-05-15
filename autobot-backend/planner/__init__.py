# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Planner Module

LLM-powered task planning with numbered pseudocode steps.
Inspired by Manus and Devin agent architectures.

Components:
- types: Plan and step data structures
- planner: Planner interface and LLM implementation

Usage:
    from planner import PlannerModule, ExecutionPlan, PlanStep

    planner = PlannerModule(llm_client, event_stream)

    # Create plan
    plan = await planner.create_plan("Implement user authentication")

    # Execute steps
    for step in plan.get_next_executable_steps():
        await planner.start_step(plan.plan_id, step.step_id)
        # ... execute step ...
        await planner.complete_step(plan.plan_id, step.step_id)
"""

from planner.planner import LLMPlannerModule, PlannerModule
from planner.types import ExecutionPlan, PlanStatus, PlanStep, StepStatus

__all__ = [
    # Types
    "StepStatus",
    "PlanStatus",
    "PlanStep",
    "ExecutionPlan",
    # Planner
    "PlannerModule",
    "LLMPlannerModule",
]
