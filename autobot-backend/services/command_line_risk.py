# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""How a shell command's risk feeds the AI-line resolver (#19950, #16840).

Two inputs to ``services.ai_line_enforcement.resolve_action_line`` live here so the resolver stays one decision:

* a command that only reads is unmanaged (#19950);
* a command a person already said "approve similar commands in future" to runs unheld for that person (#16840).

The learned rules are ONE set, shared by the chat tool seam and the agent terminal (``shared_approval_manager``),
and every rule belongs to the user who created it, keyed by the verified user id. A rule can only turn a line-2
hold into a run, and only for a SAFE or MODERATE command: a destructive or unknown-risk command always asks,
and nothing here touches line 3.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Optional

from autobot_shared.ai_lines import AiLine, LineResolution
from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import CommandRisk
from autobot_shared.tool_catalogue import SHELL_EXEC_TOOLS, canonical_tool_name
from services.command_approval_manager import CommandApprovalManager

logger = get_logger(__name__)

SOURCE_LEARNED_RULE = "learned_rule"
LEARNABLE_RISKS = frozenset({CommandRisk.SAFE, CommandRisk.MODERATE})
_manager: Optional[CommandApprovalManager] = None


def shared_approval_manager() -> CommandApprovalManager:
    """The one approval manager, and so the one learned-rule set, for chat and the agent terminal."""
    global _manager
    if _manager is None:
        _manager = CommandApprovalManager()
    return _manager


def _shell_command(tool_name: str, params: Optional[Mapping[str, Any]]) -> Optional[str]:
    command = (params or {}).get("command") if canonical_tool_name(tool_name) in SHELL_EXEC_TOOLS else None
    return command if command and isinstance(command, str) else None


def assess_command_risk(command: str) -> Optional[CommandRisk]:
    """The command's risk, or ``None`` when the classifier cannot answer (callers fail closed)."""
    try:
        from secure_command_executor import SecureCommandExecutor

        return SecureCommandExecutor(use_docker_sandbox=False).assess_command_risk(command)[0]
    except Exception as exc:  # noqa: BLE001 - fail closed on an unreadable verdict
        logger.error("Command risk unreadable (%s); the command keeps its tool's line", exc)
        return None


def is_read_only_command(tool_name: str, params: Optional[Mapping[str, Any]]) -> bool:
    """Whether this call is a shell command rated SAFE that also only reads (#19950).

    The tool name says only "runs a command", so the command decides. SAFE alone is not enough: it covers
    ``git push`` and ``curl -X POST``. No command, or a classifier that cannot answer, is not read-only:
    the call keeps the tool's own line.
    """
    command = _shell_command(tool_name, params)
    if not command or assess_command_risk(command) is not CommandRisk.SAFE:
        return False
    from security.read_only_commands import is_read_only_command as only_reads

    return only_reads(command)


async def lift_by_learned_rule(
    resolution: LineResolution,
    tool_name: str,
    params: Optional[Mapping[str, Any]],
    user_id: Any,
    *,
    applies: bool = True,
) -> LineResolution:
    """Line 1 for a line-2 shell command that one of *user_id*'s own learned rules matches; else unchanged."""
    command = _shell_command(tool_name, params)
    if not (applies and user_id and command) or resolution.line is not AiLine.DRAFT_THEN_SEND:
        return resolution
    risk = assess_command_risk(command)
    if risk not in LEARNABLE_RISKS:
        return resolution
    if not await shared_approval_manager().check_auto_approve_rules(str(user_id), command, risk.value):
        return resolution
    logger.info("Command auto-approved by a learned rule: %s (user: %s, risk: %s)", command, user_id, risk.value)
    return dataclasses.replace(resolution, line=AiLine.AUTONOMOUS, source=SOURCE_LEARNED_RULE)
