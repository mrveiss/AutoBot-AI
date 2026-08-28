# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Execution outcomes for agent terminal commands (#15073).

"The command never ran" and "the command ran and a step after it raised" are
two different events with two different fixes, and they used to close the same
way: one `except Exception` around execution *and* post-processing turned both
into ``{"status": "error", "error": "Command execution failed"}``. A signature
mismatch in a logging helper was reported to the user as a failed command, and
the stdout/stderr/return_code the command really produced were dropped on the
floor.

So the two outcomes are built here, once, and they are not interchangeable:

* ``execution_failed_response`` -- the command did not produce a result.
* ``post_execution_failed_response`` -- it did; the result travels with the
  failure, and ``error_code`` says which of the two happened.

``error_code`` is an identifier, never prose: the frontend maps it to a
translated string (``ui.commandPermission.*``), so no user-facing English is
minted in the backend. ``error`` stays English on purpose -- it is what the
agent-facing tool layer and the log read, neither of which is localised.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from type_defs.common import Metadata

# Wire values. Kept as module constants so callers and tests cannot drift.
EXECUTION_FAILED_CODE = "executionFailed"
#: #15110: the command never reached the executor because no terminal
#: session could be established. Distinct from EXECUTION_FAILED_CODE, which
#: means the session existed and the command itself did not produce a result.
SESSION_SETUP_FAILED_CODE = "sessionSetupFailed"
POST_EXECUTION_FAILED_CODE = "postExecutionFailed"
POST_EXECUTION_FAILED_STATUS = "completed_with_errors"


class PostExecutionError(Exception):
    """A command ran to completion and a step after it raised.

    Carries the executor's real result so the caller can still return the
    output the command actually produced.
    """

    def __init__(self, result: "Metadata", cause: BaseException) -> None:
        super().__init__(f"{type(cause).__name__}: {cause}")
        self.result = result
        self.cause = cause


@contextmanager
def post_execution_guard(result: "Metadata") -> Iterator[None]:
    """Mark every failure raised inside the block as post-execution.

    The guard opens *after* the executor returned, so anything it catches is by
    construction a defect in what happens after the command ran -- including
    the `TypeError` / `AttributeError` a broad catch upstream would otherwise
    have relabelled as an execution failure.
    """
    try:
        yield
    except PostExecutionError:
        raise
    except Exception as exc:
        raise PostExecutionError(result, exc) from exc


def execution_failed_response(command: str) -> "Metadata":
    """The command produced no result: there is nothing to report but the failure."""
    return {
        "status": "error",
        "error": "Command execution failed",
        "error_code": EXECUTION_FAILED_CODE,
        "command": command,
    }


def post_execution_failed_response(command: str, exc: PostExecutionError) -> "Metadata":
    """The command ran; a step after it failed. The real result is preserved."""
    response = dict(exc.result)
    response.update(
        {
            "status": POST_EXECUTION_FAILED_STATUS,
            "command_status": exc.result.get("status"),
            "command": command,
            "error": f"Command ran; a post-execution step failed: {exc}",
            "error_code": POST_EXECUTION_FAILED_CODE,
            "post_execution_error": str(exc),
        }
    )
    return response
