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

from backend.services.command_approval_manager import AgentRole
from backend.type_defs.common import Metadata


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
    running_command_task: Optional[asyncio.Task] = None  # Track running command for cancellation
