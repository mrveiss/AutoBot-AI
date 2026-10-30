# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The record of a chat command that the model's next prompt is built from (Issue #315, #19951)."""

from typing import Any, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _create_execution_result(command: str, host: str, result: dict[str, Any], approved: bool = False) -> dict[str, Any]:
    """Create standardized execution result record (Issue #315: extracted).

    Args:
        command: The command that was executed
        host: Target host
        result: Execution result dict
        approved: Whether user approved the command

    Returns:
        Standardized execution result dict for continuation loop
    """
    # #14141: `status` is derived from the exit code, not hardcoded. It used to
    # be the literal "success" regardless of `return_code`, and this dict feeds
    # `_format_execution_step`, which prints `- Status: {status}` straight into
    # the model's continuation prompt. So a command that failed was reported to
    # the model as having succeeded, with stderr as the only hint — and a test
    # runner writes its failure report to *stdout*, so the model saw a
    # full-looking report under "success" and no signal that the suite failed.
    #
    # Reachability, so nobody mistakes this for the protection: both call sites
    # are gated on ``status == "success"`` upstream (`_handle_approved_command`
    # at the approval branch, `_handle_successful_command` in
    # `_dispatch_command_by_status`), so this mapping cannot currently observe a
    # non-zero code. It is kept as a correct restatement of the invariant for
    # the day a caller stops gating -- not deleted, because a dict feeding the
    # model's prompt with a hardcoded "success" is exactly the defect that got
    # filed. The single *reachable* decision is
    # `command_executor._build_pty_result`, which every layer here propagates
    # rather than re-derives; that is where the invariant is asserted.
    return_code = result.get("return_code", 0)
    return {
        "command": command,
        "host": host,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "return_code": return_code,
        "status": _status_for_return_code(return_code),
        "approved": approved,
    }


def _status_for_return_code(return_code: Any) -> str:
    """Map an exit code to the status the model is shown (#14141).

    Only an exit code that is *known* to be 0 reports success. `None` — the
    shape an execution path produces when it never captured one — and anything
    unparseable both report ``error``, because "we do not know whether that
    worked" is far closer to failure than to success as far as the next turn is
    concerned. Reporting an unknown outcome as success is the defect this
    function exists to remove, and defaulting it would reintroduce it.
    """
    try:
        return "success" if int(return_code) == 0 else "error"
    except (TypeError, ValueError):
        logger.warning("[#14141] unusable return_code %r — reporting the step as error, not success", return_code)
        return "error"


def current_terminal_session(terminal_tool: Any, session_id: str, turn_start_id: str) -> str:
    """The session now live for this chat: the turn's own id may be gone if the PTY was recreated."""
    live = terminal_tool.active_sessions.get(session_id) if terminal_tool else None
    return live or turn_start_id


def command_params(tool_call: dict[str, Any]) -> tuple[str, str, str]:
    """``(command, host, description)`` from an ``execute_command`` call (Issue #620)."""
    params = tool_call["params"]
    return params.get("command"), params.get("host", "main"), tool_call.get("description", "")


def approval_result_of(last_command: dict[str, Any]) -> dict[str, Any]:
    """The finished command's result; a denial keeps its reason in ``denial_reason``, outside the result (#19951)."""
    result = dict(last_command.get("result", {}))
    reason = last_command.get("denial_reason")
    if reason and not result.get("error"):
        result["error"] = reason
    return result


def _unsuccessful_approval_record(
    command: str, host: str, approval_result: Optional[dict[str, Any]], explanation: str
) -> dict[str, Any]:
    """What the model is told when an approval did not end in a success (#19951).

    A rejected command and an approved one that failed report their own status and output. With no
    result this turn saw no outcome: still waiting, or a poll that lost track of it. The record claims neither.
    """
    result = approval_result or {}
    return {
        "command": command,
        "host": host,
        "status": result.get("status") or ("denied" if approval_result else "outcome_unknown"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr") or explanation,
    }
