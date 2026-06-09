# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Orchestrator prompt templates — extracted from orchestrator.py (#5060)."""

from autobot_shared.prompt_rules import LEDGER_VS_EXECUTOR_RULE

_PLANNING_PROMPT_TEMPLATE = """\
        You are an expert workflow planner. Analyze this goal and create an execution plan.

        Goal: {goal}

        Available agents and their capabilities:
        {capabilities_json}

        {ledger_rule}

        Create a workflow plan with:
        1. Required agents and their specific tasks
        2. Task dependencies (which tasks must complete before others)
        3. Execution strategy (sequential, parallel, pipeline, collaborative)
        4. Success criteria
        5. Estimated duration and resource requirements

        Respond in JSON format:
        {{
            "strategy": "parallel|sequential|pipeline|collaborative",
            "tasks": [
                {{
                    "agent": "agent_type",
                    "action": "specific_action",
                    "inputs": {{}},
                    "dependencies": ["task_ids"],
                    "priority": 1-10,
                    "capabilities_required": ["capability_names"]
                }}
            ],
            "success_criteria": ["criteria1", "criteria2"],
            "estimated_duration": 60.0,
            "resource_requirements": {{}}
        }}
        """


def build_planning_prompt(goal: str, capabilities_json: str) -> str:
    """Render the workflow planning prompt."""
    return _PLANNING_PROMPT_TEMPLATE.format(
        goal=goal,
        capabilities_json=capabilities_json,
        ledger_rule=LEDGER_VS_EXECUTOR_RULE,
    )
