# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which recorded steps actually ran (#21959).

The continuation prompt tells the model what was executed. Only a step known to have run counts; one that is
still waiting for a person, was refused, was denied, timed out or has an unknown status did not run.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable

#: Statuses that mean the action ran. Each has a producer in the chat workflow:
#: ``success`` -- ``command_execution_record._create_execution_result`` and every tool handler;
#: ``executed`` -- the compose handler (``tool_handler.py``, ``{"tool": "compose", "status": "executed"}``);
#: ``completed`` -- the delegate handler (``tool_handler.py``, ``{"tool": "delegate", "status": "completed"}``).
RAN_STATUSES = frozenset({"success", "executed", "completed"})


def _failed_after_running(step: Dict[str, Any]) -> bool:
    """A ``error`` record that carries a real exit code or output: the command ran and failed.

    ``_create_execution_result`` maps a non-zero ``return_code`` to ``error``. A refusal (the terminal's
    permission-denied response, a blocked session) is also ``error`` but has neither exit code nor output.
    """
    return step.get("return_code") is not None or bool(step.get("stdout") or step.get("output"))


def exit_code_field(result: Dict[str, Any]) -> Dict[str, Any]:
    """``{"return_code": n}`` when *result* carries a real exit code; ``{}`` for a command that never ran.

    A refusal has no exit code, and inventing one would count it as a run that failed. The key is omitted,
    never set to ``None`` (#14148), so a refused step stays NOT RUN.
    """
    code = result.get("return_code")
    return {} if code is None else {"return_code": code}


def did_execute(step: Dict[str, Any]) -> bool:
    """Whether *step* ran. Fails closed: an unknown or missing status is a step that did not run."""
    status = str(step.get("status", "")).lower()
    return status in RAN_STATUSES or (status == "error" and _failed_after_running(step))


def executed_count(steps: Iterable[Dict[str, Any]]) -> int:
    """How many of *steps* actually ran."""
    return sum(1 for step in steps if did_execute(step))


def not_run_note(step: Dict[str, Any]) -> str:
    """The line that tells the model a step did not run; empty for a step that did."""
    if did_execute(step):
        return ""
    return "\n- NOT RUN: this step did not execute (it is not complete; do not report it as done)"


#: How much of a failed command's output the error message carries (#22250).
FAILURE_TAIL_LINES = 5
FAILURE_TAIL_CHARS = 600
NO_FAILURE_DETAIL = "Command failed with no error detail"


def failure_detail(result: Dict[str, Any]) -> str:
    """Why a command failed: its own error, else ``exit N: <last output lines>`` (#22250).

    The PTY combines the streams, so ``stderr`` is empty and the cause sits in stdout. The placeholder is only
    for a result with no error, no output and no exit code.
    """
    if result.get("error"):
        return str(result["error"])
    output = "\n".join(str(result.get(key) or "") for key in ("stderr", "stdout"))
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    tail = "\n".join(lines[-FAILURE_TAIL_LINES:])[-FAILURE_TAIL_CHARS:]
    code = result.get("return_code")
    prefix = f"exit {code}" if code is not None else ""
    if prefix and tail:
        return f"{prefix}: {tail}"
    return prefix or tail or NO_FAILURE_DETAIL
