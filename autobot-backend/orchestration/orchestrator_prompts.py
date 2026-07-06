# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Orchestrator prompt templates — extracted from orchestrator.py (#5060)."""

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.prompt_rules import LEDGER_VS_EXECUTOR_RULE

logger = get_logger(__name__)

_PLANNING_PROMPT_TEMPLATE = """\
        You are an expert workflow planner. Analyze this goal and create an execution plan.

        Goal: {goal}

        Available agents and their capabilities:
        {capabilities_json}

        {ledger_rule}
        {learned_template_section}
        {similar_trajectories_section}
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


def _render_learned_template_section(learned_prompt_template: str | None, goal: str) -> str:
    """Render the learned-template advisory block for #10580.

    Performs variable substitution for ``{goal}`` in the stored template so the
    planner sees a goal-specific hint rather than the raw placeholder string.
    Returns an empty string when no template is available.
    """
    if not learned_prompt_template:
        return ""
    try:
        rendered = learned_prompt_template.format(goal=goal)
    except (KeyError, ValueError):
        rendered = learned_prompt_template
    return f"\n        Learned approach for this task type:\n        {rendered}\n"


def _render_similar_trajectories_section(similar_trajectories: List[Any] | None) -> str:
    """Render few-shot priors from high-reward trajectories for #10581.

    Injects a compact block describing proven decompositions from similar past
    tasks so the planner can reuse them as starting points.  Each trajectory
    contributes its ``action_sequence`` and ``strategy`` fields.

    Returns an empty string when ``similar_trajectories`` is empty or None so
    behaviour is fully unchanged when no similar task was found.
    """
    if not similar_trajectories:
        return ""
    lines = ["\n        Similar high-reward tasks solved previously (use as advisory priors):"]
    for traj in similar_trajectories[:3]:  # cap at 3 to keep prompt lean
        traj_dict: Dict[str, Any] = traj.to_dict() if hasattr(traj, "to_dict") else dict(traj)
        task_text = str(traj_dict.get("task_text", ""))[:120]
        strategy = traj_dict.get("strategy", "unknown")
        reward = traj_dict.get("reward", 0.0)
        actions = traj_dict.get("action_sequence", [])
        action_summary = ", ".join(
            str(a.get("action", a.get("agent", a))) if isinstance(a, dict) else str(a) for a in actions[:5]
        )
        lines.append(
            f"        - Task: {task_text!r} | strategy={strategy} " f"reward={reward:.2f} | steps: [{action_summary}]"
        )
    return "\n".join(lines) + "\n"


def build_planning_prompt(
    goal: str,
    capabilities_json: str,
    *,
    learned_prompt_template: str | None = None,
    similar_trajectories: List[Any] | None = None,
) -> str:
    """Render the workflow planning prompt.

    #10580: Accepts ``learned_prompt_template`` from a high-confidence
    LearnedStrategy and injects it as an advisory hint before the task list.
    #10581: Accepts ``similar_trajectories`` (Trajectory objects or dicts) and
    injects a few-shot prior block so the planner can reuse proven decompositions.
    Both kwargs default to None — callers that do not supply them get the
    identical prompt as before.
    """
    return _PLANNING_PROMPT_TEMPLATE.format(
        goal=goal,
        capabilities_json=capabilities_json,
        ledger_rule=LEDGER_VS_EXECUTOR_RULE,
        learned_template_section=_render_learned_template_section(learned_prompt_template, goal),
        similar_trajectories_section=_render_similar_trajectories_section(similar_trajectories),
    )
