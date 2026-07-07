# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Governed subagent delegation runner (GH#11207).

Wires the (previously unwired) ``delegate`` tool to an isolated subagent runner:
a delegated subtask runs as a *governed autonomous agent* whose ``forbidden_work``
manifest constrains it — agent autonomy with backend-enforced oversight, without
re-entering the chat pipeline.

Provider-agnostic by design: ``run_delegated_subtask`` dispatches to a named
engine. This module ships the **claude_code** engine (an ``ExecutionBackend`` that
runs its own tool loop, governed via ``--disallowedTools`` from the profile — see
GH#11188); the in-process internal-LLM engine is a follow-up that registers here.

OFF by default (``AUTOBOT_DELEGATION_ENABLED``) so the live chat path is unchanged
until delegation is explicitly enabled and validated.
"""

import os
from typing import Awaitable, Callable, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Master switch — delegate tool keeps its current (record-only) behaviour when off.
DELEGATION_ENABLED: bool = os.environ.get("AUTOBOT_DELEGATION_ENABLED", "").lower() in ("1", "true", "yes")
# Bound on how deep delegation may nest (defence against runaway delegation).
MAX_DELEGATION_DEPTH: int = int(os.environ.get("AUTOBOT_MAX_DELEGATION_DEPTH", "2"))

# AutoBot ``forbidden_work`` token → claude_code CLI tool name to disallow. claude_code
# exposes coarse tools (Bash/Edit/Write), so shell/infra/file-mutation tokens collapse
# onto them. An unmapped token is simply not disallowed (fail-open on that token, but
# the profile's other tokens still constrain the agent).
_CLAUDE_TOOL_FOR: Dict[str, str] = {
    "bash": "Bash",
    "shell": "Bash",
    "execute_command": "Bash",
    "run_command": "Bash",
    "system_exec": "Bash",
    "terminal": "Bash",
    "deploy": "Bash",
    "ansible": "Bash",
    "docker": "Bash",
    "kubectl": "Bash",
    "helm": "Bash",
    "terraform": "Bash",
    "delete_file": "Bash",
    "remove_directory": "Bash",
    "move_file": "Bash",
    "copy_file": "Bash",
    "create_directory": "Bash",
    "write_file": "Write",
    "edit_file": "Edit",
}


def forbidden_to_claude_tools(forbidden: "frozenset[str] | list[str]") -> List[str]:
    """Map a profile's ``forbidden_work`` tokens to claude_code ``--disallowedTools``."""
    return sorted({_CLAUDE_TOOL_FOR[f] for f in forbidden if f in _CLAUDE_TOOL_FOR})


async def _run_claude_code_subagent(task: str, agent_type: str, depth: int) -> str:
    """Run *task* as a governed claude_code subagent; return its output."""
    from orchestration.agent_registry import resolve_forbidden_tools
    from services.execution.base_backend import ExecutionTask
    from services.execution.claude_code_backend import build_claude_code_backend

    disallowed = forbidden_to_claude_tools(resolve_forbidden_tools(agent_type))
    exec_task = ExecutionTask(
        task_id=f"delegate-{agent_type}-d{depth}",
        code=task,
        # ``delegation_depth`` is informational for the external claude_code engine
        # (it runs out-of-process, so its own ctx never reads this back). Recursion
        # depth is only enforced for delegation initiated within one AutoBot process.
        metadata={"disallowed_tools": disallowed, "delegation_depth": depth + 1},
    )
    logger.info("delegation: claude_code subagent agent=%s depth=%d disallowed=%s", agent_type, depth, disallowed)
    result = await build_claude_code_backend().execute(exec_task)
    return result.stdout or result.stderr or ""


# Engine registry — the internal-LLM engine registers here in a follow-up (GH#11207).
_ENGINES: Dict[str, Callable[[str, str, int], Awaitable[str]]] = {
    "claude_code": _run_claude_code_subagent,
}


async def run_delegated_subtask(
    task: str, agent_type: str = "research_agent", depth: int = 0, engine: str = "claude_code"
) -> str:
    """Run a delegated subtask as a governed subagent (GH#11207).

    Raises ``ValueError`` past ``MAX_DELEGATION_DEPTH`` or for an unknown engine.
    """
    if depth >= MAX_DELEGATION_DEPTH:
        raise ValueError(f"max delegation depth {MAX_DELEGATION_DEPTH} reached (depth={depth})")
    runner = _ENGINES.get(engine)
    if runner is None:
        raise ValueError(f"unknown delegation engine: {engine!r} (available: {sorted(_ENGINES)})")
    return await runner(task, agent_type, depth)
