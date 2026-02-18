# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Command Execution Queue - Single Source of Truth for Command Lifecycle

This module implements a proper command tracking system that:
1. Links terminal sessions to chat conversations
2. Tracks command approval state persistently
3. Stores command output centrally
4. Survives backend restarts
5. Enables event-driven architecture (no timeouts!)
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from backend.type_defs.common import Metadata


class CommandState(Enum):
    """Command execution lifecycle states"""

    PENDING_APPROVAL = "pending_approval"  # Waiting for user approval
    APPROVED = "approved"  # User approved, ready to execute
    DENIED = "denied"  # User denied
    EXECUTING = "executing"  # Currently executing
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Execution failed
    CANCELLED = "cancelled"  # User cancelled


# Issue #380: Module-level frozenset for finished command states
_FINISHED_COMMAND_STATES = frozenset(
    {
        CommandState.COMPLETED,
        CommandState.FAILED,
        CommandState.DENIED,
        CommandState.CANCELLED,
    }
)


class RiskLevel(Enum):
    """Command risk assessment levels"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class CommandExecution:
    """
    Represents a single command execution with full lifecycle tracking.

    This is the SINGLE SOURCE OF TRUTH for command state.
    All systems (approval UI, execution, output collection) reference this.
    """

    # Identifiers - link everything together
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    terminal_session_id: str = ""  # PTY session ID
    chat_id: str = ""  # Conversation ID (for linking)

    # Command details
    command: str = ""
    purpose: str = ""  # Why this command (for approval UI)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_reasons: list[str] = field(default_factory=list)

    # State tracking
    state: CommandState = CommandState.PENDING_APPROVAL

    # Execution results
    output: Optional[str] = None  # stdout
    stderr: Optional[str] = None  # stderr
    return_code: Optional[int] = None

    # Timestamps - full lifecycle tracking
    requested_at: float = field(default_factory=time.time)
    approved_at: Optional[float] = None
    denied_at: Optional[float] = None
    execution_started_at: Optional[float] = None
    execution_completed_at: Optional[float] = None

    # Approval metadata
    approved_by_user_id: Optional[str] = None
    approval_comment: Optional[str] = None

    # Additional metadata
    metadata: Metadata = field(default_factory=dict)

    def to_dict(self) -> Metadata:
        """Convert to dictionary for storage/API"""
        return {
            "command_id": self.command_id,
            "terminal_session_id": self.terminal_session_id,
            "chat_id": self.chat_id,
            "command": self.command,
            "purpose": self.purpose,
            "risk_level": self.risk_level.value,
            "risk_reasons": self.risk_reasons,
            "state": self.state.value,
            "output": self.output,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "requested_at": self.requested_at,
            "approved_at": self.approved_at,
            "denied_at": self.denied_at,
            "execution_started_at": self.execution_started_at,
            "execution_completed_at": self.execution_completed_at,
            "approved_by_user_id": self.approved_by_user_id,
            "approval_comment": self.approval_comment,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Metadata) -> "CommandExecution":
        """Create from dictionary (from storage/API)"""
        return cls(
            command_id=data.get("command_id", str(uuid.uuid4())),
            terminal_session_id=data.get("terminal_session_id", ""),
            chat_id=data.get("chat_id", ""),
            command=data.get("command", ""),
            purpose=data.get("purpose", ""),
            risk_level=RiskLevel(data.get("risk_level", "MEDIUM")),
            risk_reasons=data.get("risk_reasons", []),
            state=CommandState(data.get("state", "pending_approval")),
            output=data.get("output"),
            stderr=data.get("stderr"),
            return_code=data.get("return_code"),
            requested_at=data.get("requested_at", time.time()),
            approved_at=data.get("approved_at"),
            denied_at=data.get("denied_at"),
            execution_started_at=data.get("execution_started_at"),
            execution_completed_at=data.get("execution_completed_at"),
            approved_by_user_id=data.get("approved_by_user_id"),
            approval_comment=data.get("approval_comment"),
            metadata=data.get("metadata", {}),
        )

    def approve(self, user_id: str, comment: Optional[str] = None):
        """Mark command as approved"""
        self.state = CommandState.APPROVED
        self.approved_at = time.time()
        self.approved_by_user_id = user_id
        self.approval_comment = comment

    def deny(self, user_id: str, comment: Optional[str] = None):
        """Mark command as denied"""
        self.state = CommandState.DENIED
        self.denied_at = time.time()
        self.approved_by_user_id = user_id
        self.approval_comment = comment

    def start_execution(self):
        """Mark command as executing"""
        self.state = CommandState.EXECUTING
        self.execution_started_at = time.time()

    def complete(self, output: str, stderr: str = "", return_code: int = 0):
        """Mark command as completed"""
        self.state = CommandState.COMPLETED if return_code == 0 else CommandState.FAILED
        self.output = output
        self.stderr = stderr
        self.return_code = return_code
        self.execution_completed_at = time.time()

    def is_pending(self) -> bool:
        """Check if command is pending approval"""
        return self.state == CommandState.PENDING_APPROVAL

    def is_approved(self) -> bool:
        """Check if command is approved and ready to execute"""
        return self.state == CommandState.APPROVED

    def is_executing(self) -> bool:
        """Check if command is currently executing"""
        return self.state == CommandState.EXECUTING

    def is_finished(self) -> bool:
        """Check if command has finished (completed, failed, denied, or cancelled)"""
        return self.state in _FINISHED_COMMAND_STATES  # Issue #380
