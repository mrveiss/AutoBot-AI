# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Terminal Audit Module

Audit logging for terminal command activity.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from api.schemas_terminal import SecurityLevel
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class TerminalAuditLogger:
    """Handles audit logging for terminal sessions"""

    def __init__(
        self,
        session_id: str,
        security_level: SecurityLevel,
        user_role: str = "user",
    ) -> None:
        """Initialize audit logger with session and security context."""
        self.session_id = session_id
        self.security_level = security_level
        self.user_role = user_role
        self.audit_log: List[Dict[str, Any]] = []

    def log_activity(self, activity_type: str, data: Dict[str, Any]) -> None:
        """Log command activity for security audit trail"""
        log_entry = {
            "activity_type": activity_type,
            "session_id": self.session_id,
            "user_role": self.user_role,
            "security_level": self.security_level.value,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "data": data,
        }

        self.audit_log.append(log_entry)

        # Also log to system logger for persistent audit trail
        logger.info("Terminal audit: %s", json.dumps(log_entry))

    def log_message_received(self, message_type: str) -> None:
        """Log message received event"""
        self.log_activity(
            "message_received",
            {
                "type": message_type,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "session_id": self.session_id,
            },
        )

    def log_command_input(
        self,
        command: str,
        risk_level: str,
    ) -> None:
        """Log command input event"""
        self.log_activity(
            "command_input",
            {
                "command": command,
                "risk_level": risk_level,
                "user_role": self.user_role,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    def log_command_output(self, output_length: int) -> None:
        """Log command output event"""
        self.log_activity(
            "command_output",
            {
                "output_length": output_length,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    def log_workflow_control(self, action: str, workflow_id: str | None) -> None:
        """Log workflow control event"""
        self.log_activity(
            "workflow_control",
            {
                "action": action,
                "workflow_id": workflow_id,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    def log_resize(self, rows: int, cols: int) -> None:
        """Log terminal resize event"""
        self.log_activity(
            "terminal_resize",
            {
                "rows": rows,
                "cols": cols,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    def log_signal_sent(self, signal_name: str, success: bool) -> None:
        """Log signal sent event"""
        self.log_activity(
            "signal_sent",
            {
                "signal": signal_name,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "success": success,
            },
        )

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Get the audit log entries"""
        return self.audit_log.copy()
