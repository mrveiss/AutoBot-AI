# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run a workflow command step through the security layer (#19807).

``SecurityLayer.execute_command`` is the one command-execution path: role check,
risk assessment, deny rules, audit. A workflow step adds a ``CommandRunPolicy`` to
it -- a deadline, an output cap, a working directory, refusal instead of waiting
for an approval nobody is watching for, and redaction of the command wherever the
shared path records it. Nothing here executes a process itself.

SECURITY: the command received here has had ``${secrets.NAME}`` resolved (#2153).
It is never logged, returned or stored; the step result carries a placeholder.
"""

from __future__ import annotations

import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable, FrozenSet

from fastapi import HTTPException

from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.env_utils import env_int, env_str
from autobot_shared.logging_manager import get_logger
from autobot_shared.secret_redaction import REDACTED_PLACEHOLDER, redact_text
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.user_management.login_eligibility import login_refusal
from command_run_policy import CommandRunPolicy
from security_layer import SecurityLayer
from services.workflow_secret_service import get_workflow_secret_service
from type_defs.common import Metadata
from user_management.database import db_session_context
from user_management.services.user_service import UserService

logger = get_logger(__name__)

#: Seconds a workflow command may run before its process group is killed.
WORKFLOW_COMMAND_TIMEOUT_S = env_int("AUTOBOT_WORKFLOW_COMMAND_TIMEOUT_S", 300)
#: Bytes of stdout, and of stderr, a workflow command keeps.
WORKFLOW_COMMAND_MAX_OUTPUT_BYTES = env_int("AUTOBOT_WORKFLOW_COMMAND_MAX_OUTPUT_BYTES", 1048576)
#: Directory workflow commands run in; empty selects a dedicated temp subdirectory.
WORKFLOW_COMMAND_CWD = env_str("AUTOBOT_WORKFLOW_COMMAND_CWD", "")
_DEFAULT_CWD_NAME = "autobot-workflow-commands"
SHELL_PERMISSION = "allow_shell_execute"

get_security_layer = lazy_singleton(SecurityLayer)


class CommandStepFailed(RuntimeError):
    """A command step that did not succeed; ``result`` is the redacted step result."""

    def __init__(self, message: str, result: Metadata) -> None:
        super().__init__(message)
        self.result = result


def require_command_permission(user: dict | None) -> None:
    """Raise 403 unless *user* may run shell commands, as the terminal requires."""
    role = (user or {}).get("role")
    # Administrator first and unconditionally: check_permission passes every role when enable_auth is off.
    # A run-scoped token carries role "run_jwt" and is refused here too.
    if not is_admin_role(role) or not get_security_layer().check_permission(role, SHELL_PERMISSION):
        raise HTTPException(status_code=403, detail="Running workflow commands requires an administrator")


async def current_role(owner_id: str) -> str | None:
    """The role the account *owner_id* holds now, or None when it may not act.

    Reads the user database -- the store login authenticates against
    (``api/auth.py`` ``_authenticate_and_build_user_data``) -- by the id
    ``caller_id`` recorded, and derives the role with the function login uses. A
    missing, deleted or deactivated account yields None (``login_refusal``, the one
    rule login applies). Login has no authentication-off branch, so neither does
    this: the lookup runs in every mode, and an owner that is not an account row
    (for example the synthetic admin of an auth-off request) runs nothing.
    """
    try:
        user_id = uuid.UUID(owner_id)
    except ValueError:
        return None
    async with db_session_context() as session:
        user = await UserService(session).get_user(user_id)
    return None if user is None or login_refusal(user) else UserService.account_role(user)


def _work_dir() -> str:
    """The directory commands run in, created if it is the default one."""
    path = Path(WORKFLOW_COMMAND_CWD or Path(tempfile.gettempdir()) / _DEFAULT_CWD_NAME)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def secret_value_redactor(owner_id: str | None, names: FrozenSet[str]) -> Callable[[str], str]:
    """A redactor that masks the values of the secrets injected into this step."""

    def redact(text: str) -> str:
        if not names:
            return text
        return get_workflow_secret_service().redact_secrets(text, owner_id, resolved_names=names)

    return redact


def build_policy(value_redactor: Callable[[str], str]) -> CommandRunPolicy:
    """The policy for a workflow step; the command is recorded with values and credential text masked."""
    return CommandRunPolicy(
        timeout_s=WORKFLOW_COMMAND_TIMEOUT_S,
        max_output_bytes=WORKFLOW_COMMAND_MAX_OUTPUT_BYTES,
        cwd=_work_dir(),
        refuse_approval=True,
        redact=lambda command: redact_text(value_redactor(command)),
        redact_output=value_redactor,
    )


def _step_result(raw: Metadata, value_redactor: Callable[[str], str], started: float) -> Metadata:
    """The step result from the security layer's: real exit code and streams, secrets masked."""
    return_code = raw.get("return_code")
    return {
        "command": REDACTED_PLACEHOLDER,
        "exit_code": -1 if return_code is None else return_code,
        "stdout": value_redactor(raw.get("stdout") or ""),
        "stderr": value_redactor(raw.get("stderr") or ""),
        "execution_time": time.monotonic() - started,
        "truncated": bool(raw.get("truncated")),
    }


def _failure(raw: Metadata, result: Metadata) -> CommandStepFailed:
    """The exception for a command that was refused or exited non-zero."""
    if (raw.get("security") or {}).get("blocked"):
        result["refused"] = True
        return CommandStepFailed(f"Command refused: {result['stderr']}", result)
    return CommandStepFailed(f"Command exited with code {result['exit_code']}: {result['stderr']}", result)


def _refused(message: str, user: str | None, trigger: str) -> CommandStepFailed:
    """A step refused before the security layer ran; audited with its trigger, never exit 0."""
    get_security_layer().audit_log(
        action="command_execution_refused",
        user=user or "unknown",
        outcome="denied",
        details={"trigger": trigger, "source": "workflow_step"},
    )
    return CommandStepFailed(
        f"Command refused: {message}",
        {"refused": True, "exit_code": 1, "stdout": "", "stderr": message, "command": REDACTED_PLACEHOLDER},
    )


async def _resolve_role(user: str | None) -> str:
    """The owner's current role, or a refusal when there is none, it is not admin, or the store cannot answer."""
    if not user:
        raise _refused("the workflow records no creator to run it as", user, "no_owner")
    try:
        role = await current_role(user)
    except Exception as exc:
        logger.error("Workflow command refused: the account store could not answer (%s)", type(exc).__name__)
        raise _refused("the creator's account could not be verified", user, "store_unavailable") from exc
    if not role:
        raise _refused("the creator no longer holds an active account", user, "account_inactive")
    if not is_admin_role(role):  # independent of enable_auth, which makes every permission check pass
        raise _refused("only an administrator account may run workflow commands", user, "not_admin")
    return role


async def run_command_step(command: str, *, user: str | None, value_redactor: Callable[[str], str]) -> Metadata:
    """Run *command* as *user* in the role the account holds now; return the result or raise ``CommandStepFailed``."""
    role = await _resolve_role(user)
    started = time.monotonic()
    raw = await get_security_layer().execute_command(command, user, role, policy=build_policy(value_redactor))
    result = _step_result(raw, value_redactor, started)
    if raw.get("return_code") != 0 or (raw.get("security") or {}).get("blocked"):
        raise _failure(raw, result)
    return result
