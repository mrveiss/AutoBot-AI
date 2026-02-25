# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Terminal Models

Data classes and enums for agent terminal sessions.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from services.command_approval_manager import AgentRole
from type_defs.common import Metadata


class AgentSessionState(Enum):
    """State machine for agent terminal sessions"""

    AGENT_CONTROL = "agent_control"  # Agent executing commands
    USER_INTERRUPT = "user_interrupt"  # User requesting control
    USER_CONTROL = "user_control"  # User has control
    AGENT_RESUME = "agent_resume"  # Agent resuming after user
    AWAITING_APPROVAL = "awaiting_approval"  # Waiting for command approval


@dataclass
class AgentTerminalSession:
    """Represents an agent terminal session"""

    session_id: str
    agent_id: str
    agent_role: AgentRole
    conversation_id: Optional[str] = None  # Linked chat conversation
    host: str = "main"  # Target host (main, frontend, npu-worker, etc.)
    state: AgentSessionState = AgentSessionState.AGENT_CONTROL
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    command_queue: List[Metadata] = field(default_factory=list)
    command_history: List[Metadata] = field(default_factory=list)
    pending_approval: Optional[Metadata] = None
    metadata: Metadata = field(default_factory=dict)
    pty_session_id: Optional[str] = None  # PTY session for terminal display
    running_command_task: Optional[
        asyncio.Task
    ] = None  # Track running command for cancellation

    # === Issue #372: Feature Envy Reduction Methods ===

    def is_user_controlled(self) -> bool:
        """Check if user has control of the session (Issue #372)."""
        return self.state == AgentSessionState.USER_CONTROL

    def get_user_id(self) -> str:
        """Get user ID with fallback (Issue #372 - reduces feature envy)."""
        return self.conversation_id or "default_user"

    def has_conversation(self) -> bool:
        """Check if session has a linked conversation (Issue #372)."""
        return self.conversation_id is not None

    def set_pending_approval(
        self,
        command: str,
        description: Optional[str],
        risk_value: str,
        reasons: List[str],
        command_id: str,
        is_interactive: bool,
        interactive_reasons: List[str],
    ) -> None:
        """Set pending approval data (Issue #372 - reduces feature envy)."""
        self.pending_approval = {
            "command": command,
            "description": description,
            "risk": risk_value,
            "reasons": reasons,
            "timestamp": time.time(),
            "command_id": command_id,
            "is_interactive": is_interactive,
            "interactive_reasons": interactive_reasons,
        }

    def build_pending_response(
        self,
        command: str,
        risk_value: str,
        reasons: List[str],
        description: Optional[str],
        command_id: str,
        terminal_session_id: str,
        is_interactive: bool,
        interactive_reasons: List[str],
    ) -> Metadata:
        """Build pending approval response dict (Issue #372)."""
        return {
            "status": "pending_approval",
            "command": command,
            "risk": risk_value,
            "reasons": reasons,
            "description": description,
            "agent_role": self.agent_role.value,
            "approval_required": True,
            "command_id": command_id,
            "terminal_session_id": terminal_session_id,
            "is_interactive": is_interactive,
            "interactive_reasons": interactive_reasons,
        }

    def get_blocked_error_response(self) -> Metadata:
        """Build error response when user has control (Issue #372)."""
        return {
            "status": "error",
            "error": "User has control - agent commands blocked",
            "session_id": self.session_id,
            "state": self.state.value,
        }

    def get_permission_denied_response(
        self, permission_reason: str, command: str, risk_value: str
    ) -> Metadata:
        """Build permission denied error response (Issue #372)."""
        return {
            "status": "error",
            "error": permission_reason,
            "command": command,
            "risk": risk_value,
            "agent_role": self.agent_role.value,
        }

    def has_pending_approval(self) -> bool:
        """Check if session has pending approval (Issue #372)."""
        return self.pending_approval is not None

    def get_pending_command(self) -> Optional[str]:
        """Get pending command from approval (Issue #372)."""
        if self.pending_approval:
            return self.pending_approval.get("command")
        return None

    def get_pending_risk_level(self) -> Optional[str]:
        """Get pending command risk level (Issue #372)."""
        if self.pending_approval:
            return self.pending_approval.get("risk")
        return None

    def get_pending_command_id(self) -> Optional[str]:
        """Get pending command ID (Issue #372)."""
        if self.pending_approval:
            return self.pending_approval.get("command_id")
        return None

    def add_approved_to_history(
        self,
        command: str,
        risk_level: str,
        user_id: Optional[str],
        comment: Optional[str],
        result: Metadata,
    ) -> None:
        """Add approved command to history (Issue #372)."""
        self.command_history.append(
            {
                "command": command,
                "risk": risk_level,
                "timestamp": time.time(),
                "approved_by": user_id,
                "approval_comment": comment,
                "result": result,
            }
        )

    def add_denied_to_history(
        self,
        command: str,
        risk_level: str,
        user_id: Optional[str],
        comment: Optional[str],
    ) -> None:
        """Add denied command to history (Issue #372)."""
        self.command_history.append(
            {
                "command": command,
                "risk": risk_level,
                "timestamp": time.time(),
                "denied_by": user_id,
                "denial_reason": comment,
                "result": {"status": "denied_by_user"},
            }
        )

    def clear_pending_and_resume(self) -> None:
        """Clear pending approval and return to agent control (Issue #372)."""
        self.pending_approval = None
        self.state = AgentSessionState.AGENT_CONTROL
        self.last_activity = time.time()

    def has_pty_session(self) -> bool:
        """Check if session has an active PTY session (Issue #372)."""
        return self.pty_session_id is not None

    def has_running_task(self) -> bool:
        """Check if session has a running command task (Issue #372)."""
        return (
            self.running_command_task is not None
            and not self.running_command_task.done()
        )

    async def cancel_running_task(self) -> bool:
        """Cancel the running command task if present (Issue #372)."""
        if self.has_running_task():
            self.running_command_task.cancel()
            try:
                await self.running_command_task
            except asyncio.CancelledError:
                pass
            self.running_command_task = None
            return True
        self.running_command_task = None
        return False

    def get_cancellation_metadata(self, reason: str) -> Metadata:
        """Get metadata dict for command cancellation (Issue #372)."""
        return {
            "reason": reason,
            "terminal_session_id": self.session_id,
            "pty_session_id": self.pty_session_id,
        }

    def to_info_dict(self, pty_alive: bool = False) -> Metadata:
        """Convert to session info dict for API response (Issue #372 - reduces feature envy).

        Args:
            pty_alive: Whether PTY session is alive (checked externally)
        """
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role.value,
            "conversation_id": self.conversation_id,
            "host": self.host,
            "state": self.state.value,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "uptime": time.time() - self.created_at,
            "command_count": len(self.command_history),
            "pending_approval": self.pending_approval,
            "metadata": self.metadata,
            "pty_alive": pty_alive,
        }

    def to_persist_dict(self) -> Metadata:
        """Convert to dict for Redis persistence (Issue #372 - reduces feature envy)."""
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role.value,
            "conversation_id": self.conversation_id,
            "host": self.host,
            "state": self.state.value,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "metadata": self.metadata,
            "pty_session_id": self.pty_session_id,  # CRITICAL: Store PTY session ID
            "pending_approval": self.pending_approval,  # CRITICAL: Persist pending approvals
        }
