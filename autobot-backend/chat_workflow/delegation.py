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
engine. Two engines ship:

- **claude_code** — an ``ExecutionBackend`` that runs its own tool loop out of
  process, governed via ``--disallowedTools`` mapped from the profile (GH#11188).
- **internal** — AutoBot's own LLM driving the production continuation loop, so
  the subagent's tools flow through the ``_dispatch_tool_call`` seam and inherit
  ``forbidden_work`` enforcement for free. Runs in process, so it also threads an
  incremented ``delegation_depth`` — a nested ``delegate`` is depth-bounded.

OFF by default (``AUTOBOT_DELEGATION_ENABLED``) so the live chat path is unchanged
until delegation is explicitly enabled and validated.
"""

import os
from typing import Awaitable, Callable, Dict, List

from autobot_shared import tool_catalogue as _tc
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Master switch — delegate tool keeps its current (record-only) behaviour when off.
DELEGATION_ENABLED: bool = os.environ.get("AUTOBOT_DELEGATION_ENABLED", "").lower() in ("1", "true", "yes")
# Bound on how deep delegation may nest (defence against runaway delegation).
MAX_DELEGATION_DEPTH: int = int(os.environ.get("AUTOBOT_MAX_DELEGATION_DEPTH", "2"))

# AutoBot ``forbidden_work`` token → claude_code CLI tool name to disallow. claude_code
# exposes coarse tools (Bash/Edit/Write), so shell/infra/file-mutation tokens collapse
# onto them. The token lists are NOT duplicated here — they are derived from the
# canonical atoms in ``autobot_shared/tool_catalogue.py`` so a token added there is
# covered automatically (no drift / fail-open). ``write_file``/``edit_file`` map to the
# dedicated Write/Edit tools; every other file-mutation + all shell/infra/terminal
# tokens collapse onto Bash. An unmapped token is simply not disallowed (the profile's
# other tokens still constrain the agent).
_FILE_TOOL_FOR: Dict[str, str] = {"write_file": "Write", "edit_file": "Edit"}
_BASH_TOKENS: "frozenset[str]" = frozenset(
    _tc.INFRA_AND_SHELL_TOOLS
    + _tc.TERMINAL_TOOLS
    + _tc.FILE_DELETE_TOOLS
    + tuple(t for t in _tc.FILE_WRITE_TOOLS if t not in _FILE_TOOL_FOR)
)


def _claude_tool_for(token: str) -> "str | None":
    """Canonical ``forbidden_work`` token → claude_code tool name (or ``None``)."""
    if token in _FILE_TOOL_FOR:
        return _FILE_TOOL_FOR[token]
    return "Bash" if token in _BASH_TOKENS else None


def forbidden_to_claude_tools(forbidden: "frozenset[str] | list[str]") -> List[str]:
    """Map a profile's ``forbidden_work`` tokens to claude_code ``--disallowedTools``."""
    return sorted({tool for tool in (_claude_tool_for(f) for f in forbidden) if tool})


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


async def _run_internal_subagent(task: str, agent_type: str, depth: int) -> str:
    """Run *task* as a governed **internal-LLM** subagent; return its final text.

    Drives the production continuation loop (``_execute_llm_continuation_loop``) with
    a governed ``LLMIterationContext``: setting ``agent_context.agent_id`` makes every
    tool the subagent calls pass through ``_dispatch_tool_call``'s ``forbidden_work``
    enforcement. ``delegation_depth`` is placed on the ctx so an in-loop ``delegate``
    call is depth-bounded. No DB/session is created — the loop runs on the bare ctx.
    """
    from autobot_shared.ssot_config import config
    from chat_workflow import get_chat_workflow_manager
    from chat_workflow.models import LLMIterationContext, build_governed_identity

    session_id = f"delegate-{agent_type}-d{depth}"
    agent_ctx, work_item_id, approval_categories = build_governed_identity({"agent_id": agent_type}, session_id)
    ctx = LLMIterationContext(
        ollama_endpoint=config.ollama_endpoint,
        selected_model=config.llm.default_model,
        session_id=session_id,
        terminal_session_id=session_id,
        used_knowledge=False,
        rag_citations=[],
        workflow_messages=[],
        initial_prompt=task,
        message=task,
        agent_context=agent_ctx,
        work_item_id=work_item_id,
        requires_approval_before=approval_categories,
        context={"delegation_depth": depth + 1},
    )
    logger.info("delegation: internal subagent agent=%s depth=%d model=%s", agent_type, depth, ctx.selected_model)
    responses: List[str] = []
    # Uses the shared ChatWorkflowManager singleton — safe because the loop keys all
    # state off the per-call ctx (sessions/history never touched). The lone shared
    # instance var it toggles, ``_current_lightweight_mode``, only tags stream-cost
    # metadata (best-effort; GH#11216 tracks moving it onto ctx for full isolation).
    async for item in get_chat_workflow_manager()._execute_llm_continuation_loop(ctx):
        # The loop streams WorkflowMessages, then yields a final
        # ``(all_llm_responses, execution_history, error)`` tuple.
        if isinstance(item, tuple) and len(item) == 3:
            responses = item[0] or responses
    return "\n".join(r for r in responses if r)


# Engine registry — provider-agnostic dispatch; new engines register a name here.
_ENGINES: Dict[str, Callable[[str, str, int], Awaitable[str]]] = {
    "claude_code": _run_claude_code_subagent,
    "internal": _run_internal_subagent,
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
