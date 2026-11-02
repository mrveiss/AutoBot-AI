# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Result and history-entry builders for ``SecureCommandExecutor``.

Split out of ``secure_command_executor.py`` (#19807) so that file does not grow
past its size ceiling. These methods build plain dicts and touch no executor
state, so they live in a mixin the executor inherits.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import CommandRisk

logger = get_logger(__name__)


class CommandResultBuilders:
    """Builders for blocked/error/denied results and command-history entries."""

    def _build_blocked_result(
        self,
        risk: CommandRisk,
        reasons: List[str],
        message: str,
    ) -> Dict[str, Any]:
        """
        Build result dict for blocked/denied commands.

        Issue #281: Extracted helper for blocked result building.

        Args:
            risk: Risk level of command
            reasons: List of risk reasons
            message: Error message for stderr

        Returns:
            Result dict with error status and security info
        """
        return {
            "stdout": "",
            "stderr": message,
            "return_code": 1,
            "status": "error",
            "security": {"risk": risk.value, "reasons": reasons, "blocked": True},
        }

    def _build_error_result(
        self,
        risk: CommandRisk,
        reasons: List[str],
        error_type: str,
        error_msg: str,
    ) -> Dict[str, Any]:
        """
        Build result dict for execution errors.

        Issue #281: Extracted helper for error result building.

        Args:
            risk: Risk level of command
            reasons: List of risk reasons
            error_type: Type of error (timeout, error)
            error_msg: Error message

        Returns:
            Result dict with error status
        """
        return_code = 124 if error_type == "timeout" else 1
        security_info = {"risk": risk.value, "reasons": reasons, error_type: True}
        if error_type == "error":
            security_info["error"] = error_msg

        return {
            "stdout": "",
            "stderr": error_msg,
            "return_code": return_code,
            "status": "error",
            "security": security_info,
        }

    def _build_permission_deny_result(self, command: str, rule_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Build result dict for permission rule denied commands.

        Args:
            command: The denied command
            rule_info: Permission rule info dict

        Returns:
            Result dict with error status and permission info
        """
        logger.warning(f"Command denied by permission rule: {command}")
        description = rule_info.get("description", "Denied")
        return {
            "stdout": "",
            "stderr": f"Command denied by permission rule: {description}",
            "return_code": 1,
            "status": "error",
            "security": {
                "risk": CommandRisk.FORBIDDEN.value,
                "reasons": [rule_info.get("description", "Denied by rule")],
                "blocked": True,
                "permission_rule": rule_info,
            },
        }

    def _build_auto_approved_log_entry(
        self,
        command: str,
        risk: CommandRisk,
        reasons: List[str],
        rule_info: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Build log entry for auto-approved commands.

        Args:
            command: The command being executed
            risk: Risk level of command
            reasons: Risk assessment reasons
            rule_info: Optional permission rule info

        Returns:
            Log entry dict for command history
        """
        auto_approved_by = "permission_rule"
        if rule_info and rule_info.get("from_memory"):
            auto_approved_by = "approval_memory"

        return {
            "command": command,
            "risk": risk.value,
            "reasons": reasons,
            "timestamp": asyncio.get_running_loop().time(),
            "approved": True,
            "executed": False,
            "auto_approved_by": auto_approved_by,
        }

    def _build_standard_log_entry(self, command: str, risk: CommandRisk, reasons: List[str]) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Build standard log entry for risk-based assessment.

        Args:
            command: The command being executed
            risk: Risk level of command
            reasons: Risk assessment reasons

        Returns:
            Log entry dict for command history
        """
        return {
            "command": command,
            "risk": risk.value,
            "reasons": reasons,
            "timestamp": asyncio.get_running_loop().time(),
            "approved": False,
            "executed": False,
        }
