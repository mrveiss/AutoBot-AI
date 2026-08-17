# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Enforcement gates run at the ``_dispatch_tool_call`` production seam.

Extracted from ``chat_workflow.tool_handler`` (#14495) to keep that module
under its file-size ceiling. Every function here is a pure seam guard —
none touch ``self`` in their original form, so this module carries no state
of its own; ``ToolHandlerMixin`` keeps thin delegating methods (same names,
minus the leading underscore here) so the ``_dispatch_tool_call`` call sites
and existing test monkey-patches (``mixin._enforce_forbidden_work = ...``)
are unaffected. See ``tool_handler.py::_dispatch_tool_call`` for the calling
order and the "return the message before the guarded call" contract each
one honors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from async_chat_workflow import WorkflowMessage
from autobot_shared.logging_manager import get_logger
from autobot_shared.tool_catalogue import SENSITIVE_TOOLS, match_tool_name

if TYPE_CHECKING:
    from .models import LLMIterationContext

logger = get_logger(__name__)


def enforce_forbidden_work(
    tool_call: dict[str, Any],
    ctx: "LLMIterationContext | None",
    execution_results: list[dict[str, Any]],
) -> WorkflowMessage | None:
    """Hard-block a tool the acting agent's forbidden_work manifest forbids (GH#11145).

    Resolves the acting agent id from ``ctx.agent_context`` and matches the tool
    against that agent's manifest via the shared ``match_forbidden_tool`` matcher.
    Records the failure in ``execution_results`` and returns an error
    ``WorkflowMessage`` when the tool is forbidden, else ``None``.

    An empty manifest here means exactly one thing (GH#13588): there is no agent
    identity on the ctx, i.e. the plain ungoverned chat agent, or the id names a
    declared executor. An id the registry does not recognise resolves to the
    default boundary rather than to nothing, so a typo cannot buy free rein.
    """
    from orchestration.agent_registry import match_forbidden_tool, resolve_forbidden_tools

    agent_id = ctx.agent_context.agent_id if (ctx is not None and ctx.agent_context is not None) else None
    forbidden = resolve_forbidden_tools(agent_id)
    if not forbidden:
        return None
    tool_name = tool_call.get("name", "")
    matched = match_forbidden_tool(tool_name, forbidden)
    if matched is None:
        return None
    error = f"Tool '{tool_name}' is forbidden by agent '{agent_id}' capability manifest (matched '{matched}')"
    logger.warning(
        "[GH#11145] Blocked forbidden tool '%s' for agent '%s' (matched '%s')",
        tool_name,
        agent_id,
        matched,
    )
    execution_results.append({"tool": tool_name, "status": "error", "error": error, "forbidden_by_manifest": True})
    return WorkflowMessage(
        type="error",
        content=error,
        metadata={"tool": tool_name, "error": True, "forbidden_by_manifest": True},
    )


def enforce_config_protection(
    tool_call: dict[str, Any],
    execution_results: list[dict[str, Any]],
) -> WorkflowMessage | None:
    """Block a write that would weaken a linter/formatter config (GH#11177).

    Reuses the dependency-free ``autobot_shared.config_guard`` matcher against
    the tool's target path (``params`` for built-in tools, ``arguments`` for
    MCP). Records the failure and returns an error ``WorkflowMessage`` when the
    target is a protected config, else ``None``. ``AUTOBOT_ALLOW_CONFIG_EDITS``
    opts out.
    """
    from autobot_shared.config_guard import config_edits_allowed, protected_config_for

    if config_edits_allowed():
        return None
    args = tool_call.get("params") or tool_call.get("arguments") or {}
    matched = protected_config_for(tool_call.get("name", ""), args)
    if matched is None:
        return None
    tool_name = tool_call.get("name", "")
    error = (
        f"Editing linter/formatter config '{matched}' is blocked (config-protection): "
        f"fix the code to satisfy the gate instead of weakening it. "
        f"Set AUTOBOT_ALLOW_CONFIG_EDITS=1 for an intentional change."
    )
    logger.warning("[GH#11177] Blocked config-protection write to '%s' (tool '%s')", matched, tool_name)
    execution_results.append({"tool": tool_name, "status": "error", "error": error, "config_protection": True})
    return WorkflowMessage(
        type="error",
        content=error,
        metadata={"tool": tool_name, "error": True, "config_protection": True},
    )


def enforce_fact_forcing(
    tool_call: dict[str, Any],
    ctx: "LLMIterationContext | None",
    execution_results: list[dict[str, Any]],
) -> WorkflowMessage | None:
    """Block the first edit to an existing, uninvestigated file (GH#11178).

    Records this call's read/grep target on the turn-scoped investigated set
    (``ctx.context``), then blocks an edit to an existing file not yet read
    this turn. New files are never blocked; the block self-clears once the
    agent reads the file. Off unless ``AUTOBOT_FACT_FORCING`` is set, and a
    no-op without a ``ctx`` to carry the per-turn state.
    """
    from autobot_shared.fact_forcing_guard import (
        fact_forcing_env_enabled,
        record_investigation,
        uninvestigated_edit_path,
    )

    if not fact_forcing_env_enabled() or ctx is None:
        return None
    investigated: set[str] = ctx.context.setdefault("_fact_forcing_investigated", set())
    name = tool_call.get("name", "")
    args = tool_call.get("params") or tool_call.get("arguments") or {}
    record_investigation(name, args, investigated)
    path = uninvestigated_edit_path(name, args, investigated)
    if path is None:
        return None
    error = (
        f"Editing '{path}' is blocked (fact-forcing): read the file and its "
        f"importers/call-sites first so the change is grounded, then retry."
    )
    logger.warning("[GH#11178] Blocked fact-forcing edit to '%s' (tool '%s')", path, name)
    execution_results.append({"tool": name, "status": "error", "error": error, "fact_forcing": True})
    return WorkflowMessage(
        type="error",
        content=error,
        metadata={"tool": name, "error": True, "fact_forcing": True},
    )


async def enforce_pre_action_verifier(
    tool_call: dict[str, Any],
    ctx: "LLMIterationContext | None",
    execution_results: list[dict[str, Any]],
) -> WorkflowMessage | None:
    """Run the adversarial pre-action verifier on a sensitive tool call (#14031).

    ``PreActionVerifier`` (#10547) existed only inside the dormant ``AgentLoop``
    (no production caller — #13587/#14031); this is its first production
    caller. Scope matches the original: only tools in the canonical
    ``SENSITIVE_TOOLS`` set are verified, the same set ``AgentLoop._sensitive_tool_name``
    gated on. Gated on ``pre_action_verifier_enabled``, resolved through the
    guard profile (defaults ``True`` — ``agent_loop/types.py:266``).

    A BLOCK verdict with ``VERIFIER_HARD_BLOCK=1`` hard-blocks the call,
    preserving the original semantics exactly. Without hard-block, the call
    is held pending approval with the verifier's rationale attached — the
    same ``pending_approval`` shape ``enforce_work_item_approval`` already
    uses at this seam. A broken or unavailable verifier fails open
    (SKIP/PASS via ``PreActionVerifier.verify``) and never blocks the loop.
    """
    from autobot_shared.pre_action_verifier_guard import (
        HARD_BLOCK,
        PreActionVerifier,
        VerifierVerdict,
        pre_action_verifier_enabled,
    )

    tool_name = tool_call.get("name", "")
    if match_tool_name(tool_name, SENSITIVE_TOOLS) is None:
        return None
    if not pre_action_verifier_enabled():
        return None

    args = tool_call.get("params") or tool_call.get("arguments") or {}
    if not isinstance(args, dict):
        args = {"value": repr(args)}
    reason = tool_call.get("reason", "")
    # `session_id` is only used as an opaque trajectory/log identifier here —
    # optional like `requires_approval_before` above, so a ctx double missing
    # it (as several existing seam tests use) must not crash the guard.
    task_id = getattr(ctx, "session_id", None) if ctx is not None else None

    result = await PreActionVerifier().verify(tool_name, args, reason, task_id=task_id)
    if result.verdict != VerifierVerdict.BLOCK:
        return None

    if HARD_BLOCK:
        error = (
            f"Tool '{tool_name}' was hard-blocked by the adversarial verifier "
            f"(prob={result.refutation_probability:.2f}): {result.rationale}"
        )
        logger.warning("[#14031] verifier hard-blocked tool '%s' — %s", tool_name, result.rationale[:120])
        execution_results.append({"tool": tool_name, "status": "error", "error": error, "verifier_hard_block": True})
        return WorkflowMessage(
            type="error",
            content=error,
            metadata={"tool": tool_name, "error": True, "verifier_hard_block": True},
        )

    msg = (
        f"Action '{tool_name}' requires approval before proceeding — the adversarial "
        f"verifier flagged it (prob={result.refutation_probability:.2f}): {result.rationale}"
    )
    logger.warning("[#14031] verifier held tool '%s' pending approval — %s", tool_name, result.rationale[:120])
    execution_results.append(
        {
            "tool": tool_name,
            "status": "pending_approval",
            "reason": msg,
            "verifier_rationale": result.rationale,
            "verifier_refutation_probability": result.refutation_probability,
        }
    )
    return WorkflowMessage(
        type="approval_required",
        content=msg,
        metadata={
            "tool": tool_name,
            "approval_required": True,
            "verifier_rationale": result.rationale,
        },
    )


def enforce_repetition(
    tool_call: dict[str, Any],
    ctx: "LLMIterationContext | None",
    execution_results: list[dict[str, Any]],
) -> WorkflowMessage | None:
    """Halt a looping or stagnating agent at the live seam (#13590).

    The guard existed in ``agent_loop/`` and ran nowhere; the live path had
    only a prompt sentence and a counter for *malformed* calls. Counting is
    keyed on ``(call fingerprint, result hash)``, so a polling loop whose
    result moves is never halted — only a call reproducing a result it
    already has.

    State lives on ``ctx.context``, which is per-turn and per-session; the
    seam is concurrent across sessions, so nothing here may be module-global.
    A missing ``ctx`` is a no-op, matching the other enforcers.
    """
    from autobot_shared.repetition_guard import (  # noqa: PLC0415
        REPETITION_STATE_KEY,
        STAGNATION_STATE_KEY,
        repetition_halt_reason,
        stagnation_halt_reason,
    )

    if ctx is None:
        return None

    rep_state = ctx.context.setdefault(REPETITION_STATE_KEY, {})
    reason = repetition_halt_reason(tool_call, execution_results, rep_state)
    halt_kind = "repetition_halt"

    if reason is None:
        # Repetition catches one call re-issued; stagnation catches a run of
        # different calls whose results say nothing new. Distinct reasons,
        # because "you are repeating a call" and "you are learning nothing"
        # ask the agent for different corrections.
        stag_state = ctx.context.setdefault(STAGNATION_STATE_KEY, {})
        reason = stagnation_halt_reason(execution_results, stag_state)
        halt_kind = "stagnation_halt"

    if reason is None:
        return None

    name = tool_call.get("name", "")
    execution_results.append({"tool": name, "status": "error", "error": reason, halt_kind: True})
    return WorkflowMessage(
        type="error",
        content=reason,
        metadata={"tool": name, "error": True, halt_kind: True},
    )


def enforce_work_item_approval(
    tool_call: dict[str, Any],
    ctx: "LLMIterationContext | None",
    execution_results: list[dict[str, Any]],
) -> WorkflowMessage | None:
    """Hold a tool the work item declared as approval-gated (GH#11160).

    When the run carries a work item whose ``requires_approval_before`` names
    the action category of this tool, the action is held pending approval — the
    declared gate is honored at the production seam. No work item / no matching
    category → ``None``. Categories are resolved onto the context upstream, so
    this needs no DB round-trip.
    """
    # Deferred import (mirrors chat_workflow/graph.py's own use of this
    # symbol): tool_handler imports this module at load time, so importing
    # `_approval_category_for` from tool_handler back at module scope here
    # would be circular. By call time both modules are fully loaded.
    from chat_workflow.tool_handler import _approval_category_for

    if ctx is None or not getattr(ctx, "requires_approval_before", None):
        return None
    tool_name = tool_call.get("name", "")
    category = _approval_category_for(tool_name, ctx.requires_approval_before)
    if category is None:
        return None
    work_item_id = getattr(ctx, "work_item_id", None)
    msg = (
        f"Action '{tool_name}' requires approval before proceeding — the work item "
        f"declares '{category}' as approval-gated (requires_approval_before)."
    )
    logger.warning("[GH#11160] Held tool '%s' pending approval — declared category '%s'", tool_name, category)
    execution_results.append(
        {
            "tool": tool_name,
            "status": "pending_approval",
            "reason": msg,
            "approval_category": category,
            "work_item_id": work_item_id,
        }
    )
    return WorkflowMessage(
        type="approval_required",
        content=msg,
        metadata={
            "tool": tool_name,
            "approval_required": True,
            "category": category,
            "work_item_id": work_item_id,
        },
    )
