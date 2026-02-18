# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Gateway Type Definitions

Issue #732: Unified Gateway for multi-channel communication.
Contains type definitions for messages, sessions, and channels.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List
from uuid import uuid4


class ChannelType(str, Enum):
    """Communication channel types."""

    WEBSOCKET = "websocket"
    REST_API = "rest_api"
    CLI = "cli"
    TELEGRAM = "telegram"  # Future
    DISCORD = "discord"  # Future
    SLACK = "slack"  # Future


class MessageType(str, Enum):
    """Unified message types across all channels."""

    # User messages
    USER_TEXT = "user_text"
    USER_VOICE = "user_voice"
    USER_IMAGE = "user_image"
    USER_FILE = "user_file"

    # Agent responses
    AGENT_TEXT = "agent_text"
    AGENT_THOUGHT = "agent_thought"
    AGENT_TOOL_CODE = "agent_tool_code"
    AGENT_TOOL_OUTPUT = "agent_tool_output"

    # System events
    SYSTEM_STATUS = "system_status"
    SYSTEM_ERROR = "system_error"
    SYSTEM_PROGRESS = "system_progress"

    # Session control
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_HEARTBEAT = "session_heartbeat"


class SessionStatus(str, Enum):
    """Session lifecycle status."""

    ACTIVE = "active"
    IDLE = "idle"
    PAUSED = "paused"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class UnifiedMessage:
    """
    Unified message format across all channels.

    Attributes:
        message_id: Unique message identifier
        session_id: Associated session ID
        channel: Source channel type
        message_type: Type of message
        content: Message content (text, binary, structured data)
        metadata: Additional metadata (timestamps, user info, etc.)
        created_at: Message creation timestamp
    """

    message_id: str = field(default_factory=lambda: str(uuid4()))
    session_id: str = ""
    channel: ChannelType = ChannelType.WEBSOCKET
    message_type: MessageType = MessageType.USER_TEXT
    content: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "channel": self.channel.value,
            "message_type": self.message_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedMessage":
        """Create message from dictionary."""
        return cls(
            message_id=data.get("message_id", str(uuid4())),
            session_id=data["session_id"],
            channel=ChannelType(data["channel"]),
            message_type=MessageType(data["message_type"]),
            content=data.get("content"),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.utcnow(),
        )


@dataclass
class GatewaySession:
    """
    Gateway session with isolation per user/channel.

    Attributes:
        session_id: Unique session identifier
        user_id: Associated user ID (from auth)
        channel: Source channel type
        status: Current session status
        context: Persistent context data
        message_history: List of message IDs in this session
        metadata: Additional session metadata
        created_at: Session creation timestamp
        last_activity: Last activity timestamp
        rate_limit_tokens: Remaining rate limit tokens
    """

    session_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = ""
    channel: ChannelType = ChannelType.WEBSOCKET
    status: SessionStatus = SessionStatus.ACTIVE
    context: Dict[str, Any] = field(default_factory=dict)
    message_history: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    rate_limit_tokens: int = 100  # Default rate limit

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()

    def add_message(self, message_id: str) -> None:
        """Add message to history."""
        self.message_history.append(message_id)
        self.update_activity()

    def consume_rate_limit_token(self) -> bool:
        """
        Consume a rate limit token.

        Returns:
            True if token consumed, False if rate limit exceeded
        """
        if self.rate_limit_tokens > 0:
            self.rate_limit_tokens -= 1
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "channel": self.channel.value,
            "status": self.status.value,
            "context": self.context,
            "message_history": self.message_history,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "rate_limit_tokens": self.rate_limit_tokens,
        }


@dataclass
class RoutingDecision:
    """
    Routing decision from message router.

    Attributes:
        agent_type: Type of agent to route to
        confidence: Confidence score (0.0-1.0)
        reasoning: Explanation for routing decision
        metadata: Additional routing metadata
    """

    agent_type: str
    confidence: float
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
