# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Terminal Service

Business logic layer for agent terminal access with security controls.
Integrates with SecureCommandExecutor and existing terminal infrastructure.

Security Integration:
- CVE-002 Fix: Prompt injection detection for all commands
- CVE-003 Fix: No god mode - agents subject to RBAC
- CVE-001 Fix: SSH host key verification for remote hosts
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# REUSABLE PRINCIPLE: Dependency Injection - import queue manager
from backend.models.command_execution import CommandExecution, CommandState, RiskLevel
from backend.services.command_approval_manager import (
    AgentRole,
    CommandApprovalManager,
)
from backend.services.command_execution_queue import get_command_queue
from src.chat_history_manager import (  # CRITICAL FIX: Chat integration
    ChatHistoryManager,
)
from src.chat_workflow_manager import ChatWorkflowManager  # For LLM interpretation
from src.constants.network_constants import NetworkConstants
from src.constants.path_constants import PATH
from src.logging.terminal_logger import TerminalLogger
from src.monitoring.prometheus_metrics import get_metrics_manager
from src.secure_command_executor import (
    CommandRisk,
    SecureCommandExecutor,
    SecurityPolicy,
)

# ============================================================================
# REUSABLE HELPER FUNCTIONS (Single Responsibility Principle)
# ============================================================================


def map_risk_to_level(risk: CommandRisk) -> RiskLevel:
    """
    Convert CommandRisk to RiskLevel enum.

    REUSABLE PRINCIPLE: Single function, clear responsibility, reusable across codebase.

    CommandRisk enum values: SAFE, MODERATE, HIGH, CRITICAL, FORBIDDEN
    RiskLevel enum values: LOW, MEDIUM, HIGH, CRITICAL

    Args:
        risk: CommandRisk from security assessment

    Returns:
        Corresponding RiskLevel enum
    """
    risk_mapping = {
        CommandRisk.SAFE: RiskLevel.LOW,  # Safe commands → Low risk
        CommandRisk.MODERATE: RiskLevel.MEDIUM,  # Moderate commands → Medium risk
        CommandRisk.HIGH: RiskLevel.HIGH,  # High risk commands → High risk
        CommandRisk.CRITICAL: RiskLevel.CRITICAL,  # Critical commands → Critical risk
        CommandRisk.FORBIDDEN: (
            RiskLevel.CRITICAL
        ),  # Forbidden commands → Critical risk (blocked)
    }
    return risk_mapping.get(risk, RiskLevel.MEDIUM)


def extract_terminal_and_chat_ids(session: "AgentTerminalSession") -> tuple[str, str]:
    """
    Extract terminal session ID and chat ID from agent session.

    REUSABLE PRINCIPLE: DRY - centralize ID extraction logic.

    Args:
        session: Agent terminal session

    Returns:
        Tuple of (terminal_session_id, chat_id)
    """
    terminal_session_id = session.pty_session_id or session.session_id
    chat_id = session.conversation_id or ""
    return terminal_session_id, chat_id


def create_command_execution(
    session: "AgentTerminalSession",
    command: str,
    description: str,
    risk: "CommandRisk",
    risk_reasons: list[str],
    is_interactive: bool = False,
    interactive_reasons: Optional[list[str]] = None,
) -> CommandExecution:
    """
    Create CommandExecution object from session and command details.

    REUSABLE PRINCIPLE: Factory function - encapsulates object creation logic.
    Single responsibility: Create CommandExecution, nothing else.

    Args:
        session: Agent terminal session
        command: Command to execute
        description: Command purpose/description
        risk: CommandRisk level
        risk_reasons: List of risk reasons
        is_interactive: Whether command requires stdin input (Issue #33)
        interactive_reasons: Why command is interactive (pattern matches)

    Returns:
        CommandExecution object ready to add to queue
    """
    # Use helper functions (DRY principle)
    terminal_session_id, chat_id = extract_terminal_and_chat_ids(session)
    risk_level = map_risk_to_level(risk)

    # Build metadata with interactive command info (Issue #33)
    metadata = {}
    if is_interactive:
        metadata["is_interactive"] = True
        metadata["interactive_reasons"] = interactive_reasons or []

    return CommandExecution(
        terminal_session_id=terminal_session_id,
        chat_id=chat_id,
        command=command,
        purpose=description,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
        state=CommandState.PENDING_APPROVAL,
        metadata=metadata,
    )


logger = logging.getLogger(__name__)


# ============================================================================
# INTERACTIVE COMMAND DETECTION (Issue #33)
# ============================================================================

import re

# Patterns for detecting commands that require stdin input
INTERACTIVE_COMMAND_PATTERNS = [
    r"^\s*sudo\s+",  # sudo commands (password)
    r"^\s*ssh\s+",  # SSH connections (host verification, password)
    r"\bmysql\s+.*-p\b",  # MySQL with password flag
    r"\bmysql\s+--password\b",  # MySQL with --password flag
    r"^\s*passwd\b",  # Password change commands
    r"\b--interactive\b",  # Explicit interactive flag
    r"^\s*python.*input\(",  # Python scripts with input()
    r"^\s*read\s+",  # Bash read command
    r"^\s*select\s+",  # Bash select menu
    r"^\s*apt\s+install\b",  # APT with confirmations
    r"^\s*yum\s+install\b",  # YUM with confirmations
    r"^\s*docker\s+login\b",  # Docker login (username/password)
    r"^\s*git\s+clone.*@",  # Git clone with SSH (password)
    r"^\s*psql\s+",  # PostgreSQL client
    r"^\s*ftp\s+",  # FTP client
    r"^\s*telnet\s+",  # Telnet client
]

# Compile patterns for performance
_INTERACTIVE_PATTERNS_COMPILED = [
    re.compile(pattern, re.IGNORECASE) for pattern in INTERACTIVE_COMMAND_PATTERNS
]


def is_interactive_command(command: str) -> tuple[bool, list[str]]:
    """
    Detect if a command requires interactive stdin input.

    REUSABLE PRINCIPLE: Single responsibility - only detects interactive commands.

    Args:
        command: Shell command to analyze

    Returns:
        Tuple of (is_interactive, matched_patterns)
        - is_interactive: True if command requires stdin
        - matched_patterns: List of pattern descriptions that matched

    Examples:
        >>> is_interactive_command("sudo apt update")
        (True, ["sudo commands (password)"])

        >>> is_interactive_command("ls -la")
        (False, [])

        >>> is_interactive_command("ssh user@host")
        (True, ["SSH connections (host verification, password)"])
    """
    matched_patterns = []

    for pattern, description in zip(
        _INTERACTIVE_PATTERNS_COMPILED,
        [
            "sudo commands (password)",
            "SSH connections (host verification, password)",
            "MySQL with password flag",
            "MySQL with --password flag",
            "Password change commands",
            "Explicit interactive flag",
            "Python scripts with input()",
            "Bash read command",
            "Bash select menu",
            "APT with confirmations",
            "YUM with confirmations",
            "Docker login (username/password)",
            "Git clone with SSH (password)",
            "PostgreSQL client",
            "FTP client",
            "Telnet client",
        ],
    ):
        if pattern.search(command):
            matched_patterns.append(description)

    return (len(matched_patterns) > 0, matched_patterns)


class AgentSessionState(Enum):
    """State machine for agent terminal sessions"""

    AGENT_CONTROL = "agent_control"  # Agent executing commands
    USER_INTERRUPT = "user_interrupt"  # User requesting control
    USER_CONTROL = "user_control"  # User has control
    AGENT_RESUME = "agent_resume"  # Agent resuming after user


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
    command_queue: List[Dict[str, Any]] = field(default_factory=list)
    command_history: List[Dict[str, Any]] = field(default_factory=list)
    pending_approval: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    pty_session_id: Optional[str] = None  # PTY session for terminal display
    running_command_task: Optional[asyncio.Task] = None  # Track running command for cancellation


class AgentTerminalService:
    """
    Service layer for agent terminal access with security controls.

    Features:
    - Agent session management
    - Command execution with approval workflow
    - User interrupt/takeover mechanism
    - Security integration (SecureCommandExecutor)
    - Prompt injection detection
    - Comprehensive audit logging
    """

    def __init__(
        self, redis_client=None, chat_workflow_manager=None, command_queue=None
    ):
        """
        Initialize agent terminal service.

        REUSABLE PRINCIPLE: Dependency Injection - all dependencies injected for testability.

        Args:
            redis_client: Redis client for session persistence
            chat_workflow_manager: Existing ChatWorkflowManager instance
                (prevents circular initialization)
            command_queue: Command execution queue (default: singleton instance)
        """
        self.redis_client = redis_client
        self.sessions: Dict[str, AgentTerminalSession] = {}
        self._sessions_lock = (
            asyncio.Lock()
        )  # CRITICAL: Protect concurrent session access
        self._approval_locks: Dict[str, asyncio.Lock] = {}  # Per-session approval locks
        self._approval_locks_lock = asyncio.Lock()  # Lock for the locks dictionary
        self.security_policy = SecurityPolicy()

        # Terminal command logger
        self.terminal_logger = TerminalLogger(
            redis_client=redis_client, data_dir="data/chats"
        )

        # CRITICAL FIX: Initialize ChatHistoryManager for chat integration
        self.chat_history_manager = ChatHistoryManager()

        # CRITICAL FIX: Use passed ChatWorkflowManager instead of creating new one
        # (prevents circular loop)
        self.chat_workflow_manager = chat_workflow_manager

        # REFACTOR: Use CommandApprovalManager for reusable approval logic
        self.approval_manager = CommandApprovalManager()

        # REUSABLE PRINCIPLE: Command queue - single source of truth for command state
        self.command_queue = command_queue or get_command_queue()

        # Prometheus metrics instance
        self.prometheus_metrics = get_metrics_manager()

        logger.info(
            "AgentTerminalService initialized with security controls and command queue"
        )

    async def _get_approval_lock(self, session_id: str) -> asyncio.Lock:
        """
        Get or create a per-session lock for approval operations.

        This prevents race conditions where concurrent approve/deny calls
        for the same session could both see pending_approval and execute.

        Args:
            session_id: Session identifier

        Returns:
            asyncio.Lock for this session
        """
        async with self._approval_locks_lock:
            if session_id not in self._approval_locks:
                self._approval_locks[session_id] = asyncio.Lock()
            return self._approval_locks[session_id]

    async def _cleanup_approval_lock(self, session_id: str):
        """Clean up approval lock when session is closed."""
        async with self._approval_locks_lock:
            self._approval_locks.pop(session_id, None)

    async def create_session(
        self,
        agent_id: str,
        agent_role: AgentRole,
        conversation_id: Optional[str] = None,
        host: str = "main",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentTerminalSession:
        """
        Create a new agent terminal session with PTY integration.

        Args:
            agent_id: Unique identifier for the agent
            agent_role: Role of the agent (determines permissions)
            conversation_id: Optional chat conversation ID to link
            host: Target host for command execution
            metadata: Additional session metadata

        Returns:
            Created session
        """
        session_id = str(uuid.uuid4())

        # Create PTY session for terminal display
        pty_session_id = None
        try:
            from backend.services.simple_pty import simple_pty_manager

            # Use conversation_id as PTY session ID if available, otherwise use agent session_id
            pty_session_id = conversation_id or session_id

            # Check if PTY session already exists AND is alive
            existing_pty = simple_pty_manager.get_session(pty_session_id)
            if not existing_pty or not existing_pty.is_alive():
                if existing_pty and not existing_pty.is_alive():
                    logger.warning(
                        f"PTY session {pty_session_id} exists but is dead "
                        f"(killed during restart). Recreating..."
                    )
                    # Clean up dead PTY first
                    simple_pty_manager.close_session(pty_session_id)

                # Create new PTY session
                pty = simple_pty_manager.create_session(
                    pty_session_id, initial_cwd=str(PATH.PROJECT_ROOT)
                )
                if pty:
                    logger.info(
                        f"Created PTY session {pty_session_id} for agent terminal {session_id}"
                    )
                else:
                    logger.warning(
                        f"Failed to create PTY session for agent terminal {session_id}"
                    ),
                    pty_session_id = None
            else:
                logger.info(
                    f"Reusing existing ALIVE PTY session {pty_session_id} "
                    f"for agent terminal {session_id}"
                )

            # CRITICAL: Register PTY session with terminal session_manager for WebSocket logging
            if pty_session_id and conversation_id:
                try:
                    from backend.api.terminal import session_manager

                    session_manager.session_configs[pty_session_id] = {
                        "security_level": "standard",
                        "conversation_id": conversation_id,  # Enable TerminalLogger
                    }
                    logger.info(
                        f"Registered PTY session {pty_session_id} with "
                        f"conversation_id {conversation_id} for logging"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to register PTY session with session_manager: {e}"
                    )

        except Exception as e:
            logger.error(f"Error creating PTY session: {e}")
            pty_session_id = None

        session = AgentTerminalSession(
            session_id=session_id,
            agent_id=agent_id,
            agent_role=agent_role,
            conversation_id=conversation_id,
            host=host,
            metadata=metadata or {},
            pty_session_id=pty_session_id,
        )

        # CRITICAL: Protect session dictionary access with lock
        async with self._sessions_lock:
            self.sessions[session_id] = session

        logger.info(
            f"Created agent terminal session {session_id} "
            f"for agent {agent_id} (role: {agent_role.value}), "
            f"PTY session: {pty_session_id}"
        )

        # CRITICAL: Restore pending approvals from chat history (survives restarts)
        if conversation_id:
            await self._restore_pending_approval(session, conversation_id)

        # Persist to Redis if available
        if self.redis_client:
            await self._persist_session(session)

        return session

    async def _persist_session(self, session: AgentTerminalSession):
        """Persist session to Redis"""
        try:
            key = f"agent_terminal:session:{session.session_id}"
            session_data = {
                "session_id": session.session_id,
                "agent_id": session.agent_id,
                "agent_role": session.agent_role.value,
                "conversation_id": session.conversation_id,
                "host": session.host,
                "state": session.state.value,
                "created_at": session.created_at,
                "last_activity": session.last_activity,
                "metadata": session.metadata,
                "pty_session_id": (
                    session.pty_session_id
                ),  # CRITICAL: Store PTY session ID
                "pending_approval": (
                    session.pending_approval
                ),  # CRITICAL: Persist pending approvals for page reload
            }

            import json

            # DEBUG: Log pending_approval before saving
            logger.warning(
                f"[PERSIST DEBUG] Session {session.session_id}: "
                f"pending_approval={session.pending_approval}"
            )

            json_data = json.dumps(session_data)
            await self.redis_client.setex(key, 3600, json_data)  # 1 hour TTL
            logger.debug(
                f"Persisted session {session.session_id} to Redis with key {key}"
            )

            # DEBUG: Verify what was saved
            logger.warning(
                f"[PERSIST DEBUG] Saved to Redis: "
                f"pending_approval={session_data.get('pending_approval')}"
            )
        except Exception as e:
            logger.error(f"Failed to persist session to Redis: {e}")

    async def _restore_pending_approval(
        self, session: AgentTerminalSession, conversation_id: str
    ):
        """
        Restore pending approval from chat history (survives backend restarts).

        Scans recent chat messages for unapproved command_approval_request messages
        and restores the pending_approval state so users can approve after restart.

        Args:
            session: Agent terminal session to restore state for
            conversation_id: Chat conversation ID to check
        """
        try:
            # Get recent messages from chat history (last 50 messages)
            messages = await self.chat_history_manager.get_session_messages(
                session_id=conversation_id, limit=50
            )

            if not messages:
                logger.debug(
                    f"No messages found for conversation {conversation_id}, "
                    f"skipping approval restoration"
                )
                return

            # Search for most recent command_approval_request
            approval_request = None
            for msg in reversed(messages):  # Search newest first
                if msg.get("message_type") == "command_approval_request":
                    approval_request = msg
                    break

            if not approval_request:
                logger.debug(
                    f"No pending approval requests found in conversation {conversation_id}"
                )
                return

            # Check if this approval was already responded to
            # Look for approval/denial messages AFTER the request
            request_timestamp = approval_request.get("timestamp", 0)

            for msg in reversed(messages):
                msg_time = msg.get("timestamp", 0)
                if msg_time > request_timestamp:
                    # Check if this is an approval or denial response
                    content = msg.get("text", "").lower()
                    if any(
                        keyword in content
                        for keyword in ["approved", "denied", "executed", "rejected"]
                    ):
                        logger.info(
                            f"Approval request already responded to in "
                            f"conversation {conversation_id}, "
                            f"skipping restoration"
                        )
                        return

            # Approval is still pending! Restore state from metadata
            metadata = approval_request.get("metadata", {})
            command = metadata.get("command")

            if command:
                session.pending_approval = {
                    "command": command,
                    "risk": metadata.get("risk_level", "MEDIUM"),
                    "reasons": metadata.get("reasons", []),
                    "description": metadata.get("description", ""),
                    "terminal_session_id": metadata.get("terminal_session_id"),
                    "conversation_id": conversation_id,
                    "timestamp": request_timestamp,
                }
                session.state = AgentSessionState.AWAITING_APPROVAL

                logger.info(
                    f"✅ [APPROVAL RESTORED] Restored pending approval "
                    f"for session {session.session_id}: "
                    f"command='{command}', risk={metadata.get('risk_level')}"
                )
                logger.info(
                    "✅ [APPROVAL RESTORED] User can now approve this command "
                    "even after backend restart"
                )
            else:
                logger.warning(
                    f"Found approval request but no command in metadata "
                    f"for conversation {conversation_id}"
                )

        except Exception as e:
            logger.error(f"Failed to restore pending approval from chat history: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _save_command_to_chat(
        self,
        conversation_id: str,
        command: str,
        result: dict,
        command_type: str = "agent",
    ):
        """
        Save command and output to chat history.

        Args:
            conversation_id: Chat session ID
            command: Command that was executed
            result: Command execution result with stdout/stderr
            command_type: Type of command ("agent" or "approved")
        """
        if not conversation_id:
            return

        try:
            logger.warning(
                f"[CHAT INTEGRATION] Saving {command_type} command to chat: {command[:50]}"
            )

            # Save command
            await self.chat_history_manager.add_message(
                sender="agent_terminal",
                text=f"$ {command}",
                message_type="terminal_command",
                session_id=conversation_id,
            )

            # Save output (if any)
            logger.warning(f"[CHAT INTEGRATION] Result keys: {result.keys()}")
            logger.warning(
                f"[CHAT INTEGRATION] stdout: {result.get('stdout', 'MISSING')[:100]}"
            )
            logger.warning(
                f"[CHAT INTEGRATION] stderr: {result.get('stderr', 'MISSING')[:100]}"
            )
            if result.get("stdout") or result.get("stderr"):
                output_text = (
                    result.get("stdout", "") + result.get("stderr", "")
                ).strip()
                logger.warning(
                    f"[CHAT INTEGRATION] Output text length: {len(output_text)}"
                )
                if output_text:
                    # CRITICAL FIX: Strip ANSI escape codes before saving to chat
                    from src.utils.encoding_utils import strip_ansi_codes

                    clean_output = strip_ansi_codes(output_text).strip()
                    logger.warning(
                        f"[CHAT INTEGRATION] Clean output length: {len(clean_output)}"
                    )

                    if clean_output:
                        await self.chat_history_manager.add_message(
                            sender="agent_terminal",
                            text=clean_output,  # Save cleaned output
                            message_type="terminal_output",
                            session_id=conversation_id,
                        )
                        logger.warning(
                            "[CHAT INTEGRATION] Output message saved successfully"
                        )
                else:
                    logger.warning(
                        "[CHAT INTEGRATION] Output text is empty after stripping"
                    )
            else:
                logger.warning("[CHAT INTEGRATION] No stdout or stderr in result")

            logger.warning(
                f"[CHAT INTEGRATION] {command_type.capitalize()} command saved to chat successfully"
            )
        except Exception as e:
            logger.error(
                f"[EXCEPTION] Failed to save {command_type} command to chat: {e}"
            )
            import traceback

            logger.error(f"[EXCEPTION] Traceback: {traceback.format_exc()}")

    async def get_session(self, session_id: str) -> Optional[AgentTerminalSession]:
        """
        Get session by ID. Checks memory first, then loads from Redis if needed.

        Args:
            session_id: Session identifier

        Returns:
            Session if found, None otherwise
        """
        # Fast path: check in-memory sessions first (protected by lock)
        async with self._sessions_lock:
            session = self.sessions.get(session_id)
            if session:
                logger.warning(
                    f"[GET_SESSION DEBUG] Returning in-memory session {session_id}: "
                    f"pending_approval={session.pending_approval}"
                )
                return session

        # Slow path: try loading from Redis if available
        if self.redis_client:
            try:
                import json

                key = f"agent_terminal:session:{session_id}"
                session_json = await asyncio.wait_for(
                    self.redis_client.get(key), timeout=2.0
                )

                if session_json:
                    session_data = json.loads(session_json)

                    # Reconstruct session object from Redis data
                    from .agent_terminal_session import AgentRole, SessionState

                    session = AgentTerminalSession(
                        session_id=session_data["session_id"],
                        agent_id=session_data["agent_id"],
                        agent_role=AgentRole(session_data["agent_role"]),
                        conversation_id=session_data.get("conversation_id"),
                        host=session_data.get("host"),
                        metadata=session_data.get("metadata", {}),
                        pty_session_id=session_data.get("pty_session_id"),
                    )

                    # Restore session state
                    session.state = SessionState(session_data["state"])
                    session.created_at = session_data["created_at"]
                    session.last_activity = session_data["last_activity"]
                    session.pending_approval = session_data.get(
                        "pending_approval"
                    )  # CRITICAL: Restore pending approvals

                    # Add back to memory cache (protected by lock)
                    async with self._sessions_lock:
                        self.sessions[session_id] = session

                    logger.info(f"Loaded session {session_id} from Redis persistence")
                    return session

            except asyncio.TimeoutError:
                logger.warning(f"Redis timeout loading session {session_id}")
            except Exception as e:
                logger.error(f"Failed to load session from Redis: {e}")

        # Session not found in memory or Redis
        return None

    async def list_sessions(
        self,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> List[AgentTerminalSession]:
        """
        List agent terminal sessions.

        Args:
            agent_id: Filter by agent ID
            conversation_id: Filter by conversation ID

        Returns:
            List of matching sessions
        """
        sessions = list(self.sessions.values())

        if agent_id:
            sessions = [s for s in sessions if s.agent_id == agent_id]

        if conversation_id:
            sessions = [s for s in sessions if s.conversation_id == conversation_id]

        return sessions

    async def close_session(self, session_id: str) -> bool:
        """
        Close an agent terminal session.

        Args:
            session_id: Session to close

        Returns:
            True if closed successfully
        """
        # CRITICAL: Atomic check-and-delete with lock to prevent race conditions
        async with self._sessions_lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
            else:
                return False

        logger.info(f"Closed agent terminal session {session_id}")

        # Clean up per-session approval lock
        await self._cleanup_approval_lock(session_id)

        # Remove from Redis (outside lock since Redis has its own concurrency control)
        if self.redis_client:
            try:
                key = f"agent_terminal:session:{session_id}"
                self.redis_client.delete(key)
            except Exception as e:
                logger.error(f"Failed to remove session from Redis: {e}")

        return True

    def _check_agent_permission(
        self,
        agent_role: AgentRole,
        command_risk: CommandRisk,
    ) -> tuple[bool, str]:
        """
        Check if agent has permission to execute command at given risk level.

        REFACTORED: Now uses CommandApprovalManager static method for reusability.

        Args:
            agent_role: Role of the agent
            command_risk: Risk level of the command

        Returns:
            Tuple of (allowed, reason)
        """
        return CommandApprovalManager.check_permission(
            agent_role=agent_role,
            command_risk=command_risk,
            permissions=self.approval_manager.agent_permissions,
        )

    def _needs_approval(
        self,
        agent_role: AgentRole,
        command_risk: CommandRisk,
    ) -> bool:
        """
        Check if command needs user approval.

        REFACTORED: Now uses CommandApprovalManager static method for reusability.

        In supervised mode: HIGH/CRITICAL/FORBIDDEN commands are allowed but ALWAYS require approval
        In normal mode: Only commands up to max_risk are allowed, HIGH+ require approval

        Args:
            agent_role: Role of the agent
            command_risk: Risk level of the command

        Returns:
            True if approval is required
        """
        return CommandApprovalManager.needs_approval(
            agent_role=agent_role,
            command_risk=command_risk,
            permissions=self.approval_manager.agent_permissions,
        )

    def _write_to_pty(self, session: AgentTerminalSession, text: str) -> bool:
        """
        Write text to PTY terminal display.
        Auto-recreates PTY if stale (e.g., after backend restart).

        Args:
            session: Agent terminal session
            text: Text to write to terminal

        Returns:
            True if written successfully
        """
        logger.info(
            f"[PTY_WRITE] Called for session {session.session_id}, "
            f"pty_session_id={session.pty_session_id}, text_len={len(text)}"
        )

        if not session.pty_session_id:
            logger.warning("No PTY session ID available for writing")
            return False

        try:
            from backend.services.simple_pty import simple_pty_manager

            pty = simple_pty_manager.get_session(session.pty_session_id)
            logger.info(
                f"[PTY_WRITE] Got PTY session: {pty is not None}, "
                f"alive: {pty.is_alive() if pty else 'N/A'}"
            )

            # If PTY is not alive, recreate it (handles stale sessions after restart)
            if not pty or not pty.is_alive():
                logger.warning(
                    f"[PTY_WRITE] PTY session {session.pty_session_id} not alive "
                    f"(exists={pty is not None}), recreating..."
                )

                # Create new PTY with same session ID
                new_pty = simple_pty_manager.create_session(
                    session.pty_session_id, initial_cwd=str(PATH.PROJECT_ROOT)
                )

                if new_pty:
                    logger.info(f"Recreated PTY session {session.pty_session_id}")
                    pty = new_pty
                else:
                    logger.error(
                        f"Failed to recreate PTY session {session.pty_session_id}"
                    )
                    return False

            # Write to PTY
            success = pty.write_input(text)
            if success:
                logger.debug(f"Wrote to PTY {session.pty_session_id}: {text[:50]}...")
            return success

        except Exception as e:
            logger.error(f"Error writing to PTY: {e}")
            return False

    async def cancel_command(self, session: AgentTerminalSession, reason: str = "timeout") -> bool:
        """
        Cancel a running command with graceful shutdown.

        CRITICAL FIX (Critical #3): Proper cleanup for timeouts to prevent orphaned processes.

        Process:
        1. Send SIGTERM to gracefully stop the process
        2. Wait 2-3 seconds for graceful shutdown
        3. Send SIGKILL if still running
        4. Clean up resources and log the cancellation

        Args:
            session: Agent terminal session
            reason: Reason for cancellation (default: "timeout")

        Returns:
            True if command was cancelled successfully
        """
        if not session.pty_session_id:
            logger.warning(f"[CANCEL] No PTY session to cancel for {session.session_id}")
            return False

        try:
            from backend.services.simple_pty import simple_pty_manager

            pty = simple_pty_manager.get_session(session.pty_session_id)
            if not pty or not pty.is_alive():
                logger.info(
                    f"[CANCEL] PTY session {session.pty_session_id} not alive, "
                    f"nothing to cancel"
                )
                return False

            logger.warning(
                f"[CANCEL] Cancelling command due to {reason}: "
                f"PTY {session.pty_session_id}"
            )

            # Step 1: Send SIGTERM for graceful shutdown
            try:
                # Send Ctrl+C to the shell (SIGINT)
                self._write_to_pty(session, "\x03")  # Ctrl+C
                logger.info(f"[CANCEL] Sent SIGINT (Ctrl+C) to PTY {session.pty_session_id}")
            except Exception as sigint_error:
                logger.warning(f"[CANCEL] Failed to send SIGINT: {sigint_error}")

            # Step 2: Wait 2 seconds for graceful shutdown
            await asyncio.sleep(2.0)

            # Step 3: Check if process is still running
            if pty.is_alive():
                logger.warning(
                    "[CANCEL] Process still running after SIGINT, "
                    "attempting forceful termination (SIGKILL)"
                )
                try:
                    # Close the PTY session forcefully
                    simple_pty_manager.close_session(session.pty_session_id)
                    logger.info(f"[CANCEL] Forcefully closed PTY session {session.pty_session_id}")
                except Exception as sigkill_error:
                    logger.error(f"[CANCEL] Failed to forcefully close PTY: {sigkill_error}")
                    return False
            else:
                logger.info("[CANCEL] Process terminated gracefully after SIGINT")

            # Step 4: Clean up session state
            if session.running_command_task and not session.running_command_task.done():
                session.running_command_task.cancel()
                try:
                    await session.running_command_task
                except asyncio.CancelledError:
                    logger.info(
                        f"[CANCEL] Cancelled running command task for "
                        f"session {session.session_id}"
                    )

            session.running_command_task = None

            # Log cancellation to chat history
            if session.conversation_id:
                try:
                    await self.chat_history_manager.add_message(
                        sender="system",
                        text=f"⚠️ Command cancelled due to {reason}",
                        message_type="command_cancellation",
                        session_id=session.conversation_id,
                        metadata={
                            "reason": reason,
                            "terminal_session_id": session.session_id,
                            "pty_session_id": session.pty_session_id,
                        },
                    )
                    logger.info("[CANCEL] Logged cancellation to chat history")
                except Exception as log_error:
                    logger.warning(f"[CANCEL] Failed to log cancellation to chat: {log_error}")

            logger.info(
                f"[CANCEL] ✅ Command cancellation complete for "
                f"session {session.session_id}"
            )
            return True

        except Exception as e:
            logger.error(f"[CANCEL] Error during command cancellation: {e}", exc_info=True)
            return False

    async def _detect_return_code(
        self, session: AgentTerminalSession, max_attempts: int = 10
    ) -> Optional[int]:
        """
        Detect command return code using exit code marker injection.

        SECURITY FIX (Critical #2): Uses UUID-based marker to prevent regex injection.
        Phase 1 Implementation: Injects unique marker and polls chat history with
        exponential backoff to detect the exit code.

        Args:
            session: Agent terminal session
            max_attempts: Maximum polling attempts (default: 10)

        Returns:
            Return code if detected, None if detection failed
        """
        import re

        from src.utils.encoding_utils import strip_ansi_codes

        logger.debug("[PTY_EXEC] Injecting exit code marker...")

        # SECURITY FIX (Critical #2): Generate unique UUID-based marker to prevent spoofing
        # Attack vector fixed: `echo "EXIT_CODE:0" && malicious_command` can no longer fake success
        marker_id = str(uuid.uuid4())
        marker = f"__EXIT_CODE_{marker_id}__:"

        # Inject marker to capture exit code
        marker_cmd = f"echo '{marker}'$?"
        if not self._write_to_pty(session, f"{marker_cmd}\n"):
            logger.warning("[PTY_EXEC] Failed to inject exit code marker")
            return None

        logger.debug(f"[PTY_EXEC] Injected unique marker: {marker}")

        # Poll with exponential backoff
        base_delay = 0.1  # Start with 100ms
        for attempt in range(max_attempts):
            await asyncio.sleep(base_delay * (1.5 ** attempt))  # Exponential backoff

            try:
                if not session.conversation_id:
                    continue

                # Get recent messages
                messages = await self.chat_history_manager.get_session_messages(
                    session_id=session.conversation_id, limit=3
                )

                # Search for unique EXIT_CODE marker with UUID
                for msg in reversed(messages):
                    if msg.get("sender") == "terminal" and msg.get("text"):
                        clean_text = strip_ansi_codes(msg["text"])

                        # Match unique marker pattern: __EXIT_CODE_{uuid}__:N
                        # Use re.escape to safely match the UUID
                        escaped_marker = re.escape(marker)
                        match = re.search(rf'{escaped_marker}(\d+)', clean_text)
                        if match:
                            return_code = int(match.group(1))
                            logger.info(
                                f"[PTY_EXEC] Detected return code: {return_code} "
                                f"(marker: {marker_id})"
                            )
                            return return_code

            except Exception as e:
                logger.warning(
                    f"[PTY_EXEC] Error detecting return code "
                    f"(attempt {attempt + 1}): {e}"
                )

        # Fallback: Analyze error patterns
        logger.debug("[PTY_EXEC] Marker detection failed, falling back to error pattern analysis")
        return await self._analyze_error_patterns(session)

    async def _analyze_error_patterns(self, session: AgentTerminalSession) -> int:
        """
        Fallback return code detection via error pattern analysis.

        Analyzes recent terminal output for common error indicators when
        exit code marker detection fails.

        Args:
            session: Agent terminal session

        Returns:
            Return code estimate (0 = success, 1 = error)
        """
        import re

        from src.utils.encoding_utils import strip_ansi_codes

        error_patterns = [
            r'command not found',
            r'permission denied',
            r'no such file or directory',
            r'cannot access',
            r'error:',
            r'fatal:',
            r'failed',
        ]

        try:
            if not session.conversation_id:
                return 0  # Assume success if no conversation

            messages = await self.chat_history_manager.get_session_messages(
                session_id=session.conversation_id, limit=5
            )

            for msg in reversed(messages):
                if msg.get("sender") == "terminal" and msg.get("text"):
                    clean_text = strip_ansi_codes(msg["text"]).lower()

                    for pattern in error_patterns:
                        if re.search(pattern, clean_text):
                            logger.debug(f"[PTY_EXEC] Error pattern detected: {pattern}")
                            return 1  # Error detected

        except Exception as e:
            logger.warning(f"[PTY_EXEC] Error pattern analysis failed: {e}")

        return 0  # Assume success if no errors detected

    async def _intelligent_poll_output(
        self,
        session: AgentTerminalSession,
        timeout: float = 30.0,
        stability_threshold: float = 0.5,
    ) -> str:
        """
        Intelligent polling system with adaptive timeouts and output stability detection.

        CRITICAL FIX (Critical #3): Cancels command on timeout to prevent orphaned processes.
        Phase 2 Implementation: Polls chat history with progressive backoff until
        output stabilizes (unchanged for stability_threshold seconds) or timeout.

        Args:
            session: Agent terminal session
            timeout: Maximum wait time in seconds (default: 30s)
            stability_threshold: Seconds of unchanged output to consider stable (default: 0.5s)

        Returns:
            Collected output from chat history
        """
        import time as time_module

        from src.utils.encoding_utils import strip_ansi_codes

        start_time = time_module.time()
        last_output = ""
        last_change_time = start_time
        poll_interval = 0.1  # Start with 100ms
        max_interval = 2.0  # Cap at 2 seconds

        logger.debug(
            f"[PTY_EXEC] Starting intelligent polling "
            f"(timeout={timeout}s, stability={stability_threshold}s)"
        )

        while (time_module.time() - start_time) < timeout:
            try:
                current_output = ""

                if session.conversation_id:
                    messages = await self.chat_history_manager.get_session_messages(
                        session_id=session.conversation_id, limit=5
                    )

                    # Find most recent terminal output
                    for msg in reversed(messages):
                        if msg.get("sender") == "terminal" and msg.get("text"):
                            terminal_text = msg["text"]
                            clean_output = strip_ansi_codes(terminal_text)

                            # Extract output (skip command echo)
                            lines = clean_output.split("\n")
                            if len(lines) > 1:
                                current_output = "\n".join(lines[1:]).strip()
                            break

                # Check output stability
                if current_output and current_output == last_output:
                    stable_duration = time_module.time() - last_change_time
                    if stable_duration >= stability_threshold:
                        logger.info(
                            f"[PTY_EXEC] Output stabilized after {stable_duration:.2f}s, "
                            f"total elapsed: {time_module.time() - start_time:.2f}s"
                        )
                        return current_output
                elif current_output != last_output:
                    last_output = current_output
                    last_change_time = time_module.time()
                    # Reset interval on new output
                    poll_interval = 0.1

            except Exception as e:
                logger.warning(f"[PTY_EXEC] Polling error: {e}")

            # Progressive backoff
            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, max_interval)

        # CRITICAL FIX (Critical #3): Timeout reached - cancel the running command
        elapsed = time_module.time() - start_time
        logger.warning(
            f"[PTY_EXEC] Polling timeout reached ({elapsed:.2f}s), "
            f"cancelling command to prevent orphaned processes"
        )

        # Cancel the command to clean up resources
        cancelled = await self.cancel_command(session, reason="timeout")
        if cancelled:
            logger.info("[PTY_EXEC] Successfully cancelled command after timeout")
        else:
            logger.error(
                "[PTY_EXEC] Failed to cancel command after timeout - "
                "may have orphaned process"
            )

        return last_output

    async def _execute_in_pty(
        self, session: AgentTerminalSession, command: str, timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Execute command directly in PTY shell (true collaboration mode).
        User and agent work as one in the same terminal.

        IMPROVEMENTS (Issue #143):
        - Phase 1: Intelligent return code detection with retry and fallback
        - Phase 2: Adaptive polling with output stability detection
        - Increased default timeout from 5s to 30s
        - Proper error handling and comprehensive logging

        Args:
            session: Agent terminal session
            command: Command to execute
            timeout: Max seconds to wait for output (default: 30s)

        Returns:
            Dict with status, stdout, stderr, return_code
        """
        import asyncio
        import time as time_module

        from backend.services.simple_pty import simple_pty_manager

        logger.info(f"[PTY_EXEC] Executing in PTY: {command}")

        # Write command to PTY (shell will execute it)
        if not self._write_to_pty(session, f"{command}\n"):
            return {
                "status": "error",
                "stdout": "",
                "stderr": "Failed to write command to PTY",
                "return_code": 1,
            }

        # CRITICAL FIX (Critical #1): Race Condition Prevention
        # Do NOT collect from PTY output queue directly! The WebSocket handler
        # consumes from the same queue, causing message loss (0.3-0.5s latency).
        #
        # SOLUTION: Use pub/sub pattern via chat history:
        # 1. WebSocket handler receives PTY output (subscriber 1)
        # 2. WebSocket saves output to chat history (broadcast)
        # 3. Agent terminal polls chat history (subscriber 2)
        # 4. No queue consumption race - both get complete output
        #
        # This implements the broadcast pattern recommended in code review
        # without requiring PTY architecture changes.

        # Phase 2: Intelligent polling with adaptive timeouts
        logger.info(
            f"[PTY_EXEC] Starting intelligent polling (timeout={timeout}s) "
            f"for command completion..."
        )

        full_output = await self._intelligent_poll_output(
            session=session,
            timeout=timeout,
            stability_threshold=0.5,  # 500ms stability threshold
        )

        # Phase 1: Detect return code with retry logic
        return_code = await self._detect_return_code(
            session=session,
            max_attempts=10,
        )

        # If detection failed, default to 0 (success) or analyze errors
        if return_code is None:
            logger.warning("[PTY_EXEC] Return code detection failed, using fallback")
            return_code = 0 if full_output else 1

        logger.info(
            f"[PTY_EXEC] Command execution complete. "
            f"Return code: {return_code}, Output length: {len(full_output)} chars"
        )

        return {
            "status": "success" if return_code == 0 else "error",
            "stdout": full_output,
            "stderr": "",  # PTY combines stdout/stderr
            "return_code": return_code,
        }

    async def execute_command(
        self,
        session_id: str,
        command: str,
        description: Optional[str] = None,
        force_approval: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a command in an agent terminal session.

        Security workflow:
        1. Validate session and permissions
        2. Assess command risk (SecureCommandExecutor)
        3. Check agent permissions for risk level
        4. Request user approval if needed
        5. Execute command if approved
        6. Log execution with security metadata

        Args:
            session_id: Agent session ID
            command: Command to execute
            description: Optional command description
            force_approval: Force user approval even for safe commands

        Returns:
            Execution result with security metadata
        """
        # Get session
        session = await self.get_session(session_id)
        if not session:
            return {
                "status": "error",
                "error": "Session not found",
                "session_id": session_id,
            }

        # Check session state
        if session.state == AgentSessionState.USER_CONTROL:
            return {
                "status": "error",
                "error": "User has control - agent commands blocked",
                "session_id": session_id,
                "state": session.state.value,
            }

        # Create secure command executor with approval callback
        async def approval_callback(approval_data: Dict[str, Any]) -> bool:
            """Callback for user approval requests"""
            # Store pending approval in session
            session.pending_approval = approval_data
            session.state = AgentSessionState.USER_INTERRUPT

            # Wait for user response (in real implementation, this would be async)
            # For now, we'll return False to indicate approval is needed
            logger.info(
                f"Agent command requires approval: {approval_data['command']} "
                f"(risk: {approval_data['risk']})"
            )
            return False  # Requires approval

        executor = SecureCommandExecutor(
            policy=self.security_policy,
            require_approval_callback=approval_callback,
            use_docker_sandbox=False,
        )

        # Assess command risk
        risk, reasons = executor.assess_command_risk(command)

        # Detect if command is interactive (Issue #33)
        is_interactive, interactive_reasons = is_interactive_command(command)
        if is_interactive:
            logger.info(
                f"Interactive command detected: {command} "
                f"(requires stdin: {', '.join(interactive_reasons)})"
            )

        # Check agent permissions
        allowed, permission_reason = self._check_agent_permission(
            session.agent_role, risk
        )
        if not allowed:
            logger.warning(
                f"Agent {session.agent_id} denied command execution: {permission_reason}"
            )
            return {
                "status": "error",
                "error": permission_reason,
                "command": command,
                "risk": risk.value,
                "agent_role": session.agent_role.value,
            }

        # Check if approval is needed
        # CRITICAL FIX: Force ALL commands through approval workflow
        # User wants to see and approve every command, regardless of risk level
        needs_approval = (
            True  # Always require approval (auto-approve rules still apply)
        )

        if needs_approval:
            # Check auto-approve rules (use conversation_id as user_id proxy)
            user_id = session.conversation_id or "default_user"
            is_auto_approved = await self._check_auto_approve_rules(
                user_id=user_id,
                command=command,
                risk_level=risk.value,
            )

            if is_auto_approved:
                # Auto-approve based on stored rule - treat as if user approved
                logger.info(
                    f"Command auto-approved by rule: {command} "
                    f"(user: {user_id}, risk: {risk.value})"
                )
                # Fall through to execute command below
            else:
                # REUSABLE PRINCIPLE: Use queue as single source of truth
                # Create CommandExecution object using factory function
                cmd_execution = create_command_execution(
                    session=session,
                    command=command,
                    description=description,
                    risk=risk,
                    risk_reasons=reasons,
                    is_interactive=is_interactive,  # Issue #33
                    interactive_reasons=interactive_reasons,  # Issue #33
                )

                # Add to command queue (persistent, survives restarts)
                await self.command_queue.add_command(cmd_execution)
                logger.info(
                    f"✅ [QUEUE] Added command {cmd_execution.command_id} to queue: "
                    f"terminal={cmd_execution.terminal_session_id}, chat={cmd_execution.chat_id}"
                )

                # BACKWARD COMPATIBILITY: Keep session.pending_approval for now
                # (Will be removed in Phase 4 cleanup)
                session.pending_approval = {
                    "command": command,
                    "description": description,
                    "risk": risk.value,
                    "reasons": reasons,
                    "timestamp": time.time(),
                    "command_id": cmd_execution.command_id,  # Link to queue
                    "is_interactive": is_interactive,  # Issue #33
                    "interactive_reasons": interactive_reasons,  # Issue #33
                }

                # CRITICAL: Persist session to Redis so pending approval survives page reload
                if self.redis_client:
                    await self._persist_session(session)

                logger.info(
                    f"Command requires approval: {command} "
                    f"(agent: {session.agent_id}, risk: {risk.value}, "
                    f"command_id: {cmd_execution.command_id})"
                )

                # Log pending approval command
                if session.conversation_id:
                    await self.terminal_logger.log_command(
                        session_id=session.conversation_id,
                        command=command,
                        run_type="autobot",
                        status="pending_approval",
                        user_id=user_id,
                    )

                    # CRITICAL FIX: Add approval request message to chat history
                    # This enables:
                    # 1. _restore_pending_approval to find it after backend restart
                    # 2. Frontend to display the approval dialog
                    # 3. update_message_metadata to update approval status
                    try:
                        await self.chat_history_manager.add_message(
                            session_id=session.conversation_id,
                            role="system",
                            text=f"⚠️ Command requires approval: `{command}` [Risk: {risk.value}]",
                            message_type="command_approval_request",
                            metadata={
                                "command": command,
                                "risk_level": risk.value,
                                "reasons": reasons,
                                "description": description,
                                "terminal_session_id": session.session_id,
                                "command_id": cmd_execution.command_id,
                                "requires_approval": True,
                                "agent_role": session.agent_role.value,
                            },
                        )
                        logger.info(
                            f"✅ [CHAT MESSAGE] Added command_approval_request to chat history: "
                            f"command={command}, session={session.session_id}"
                        )
                    except Exception as chat_msg_error:
                        logger.error(
                            f"Failed to add approval request to chat history: {chat_msg_error}",
                            exc_info=True,
                        )

                return {
                    "status": "pending_approval",
                    "command": command,
                    "risk": risk.value,
                    "reasons": reasons,
                    "description": description,
                    "agent_role": session.agent_role.value,
                    "approval_required": True,
                    "command_id": (
                        cmd_execution.command_id
                    ),  # CRITICAL: Return command_id to frontend
                    "terminal_session_id": (
                        cmd_execution.terminal_session_id
                    ),  # For frontend linking
                    "is_interactive": (
                        is_interactive
                    ),  # Issue #33 - Frontend can show stdin UI
                    "interactive_reasons": (
                        interactive_reasons
                    ),  # Issue #33 - Display to user
                }

        # Execute command (auto-approved safe commands)
        try:
            # Track task execution start time for Prometheus
            task_start_time = time.time()

            # Log command execution start
            if session.conversation_id:
                await self.terminal_logger.log_command(
                    session_id=session.conversation_id,
                    command=command,
                    run_type="autobot",
                    status="executing",
                    user_id=None,
                )

            # CRITICAL: Execute in PTY (true collaboration mode - works on any host)
            # User and agent work as one in the same terminal
            result = await self._execute_in_pty(session, command)

            # Record Prometheus task execution metric (success)
            task_duration = time.time() - task_start_time
            task_type = "command_execution"
            agent_type = session.agent_role.value
            status = "success" if result.get("status") == "success" else "error"
            self.prometheus_metrics.record_task_execution(
                task_type=task_type,
                agent_type=agent_type,
                status=status,
                duration=task_duration,
            )

            # Log command execution result
            if session.conversation_id:
                await self.terminal_logger.log_command(
                    session_id=session.conversation_id,
                    command=command,
                    run_type="autobot",
                    status="success" if result.get("status") == "success" else "error",
                    result=result,
                    user_id=None,
                )

            # Save command and output to chat history
            await self._save_command_to_chat(
                session.conversation_id, command, result, command_type="agent"
            )

            # CRITICAL FIX: Call LLM to interpret command results
            if session.conversation_id:
                try:
                    logger.info(
                        f"[INTERPRETATION] Starting LLM interpretation for command: {command}"
                    ),
                    interpretation = (
                        await self.chat_workflow_manager.interpret_terminal_command(
                            command=command,
                            stdout=result.get("stdout", ""),
                            stderr=result.get("stderr", ""),
                            return_code=result.get("return_code", 0),
                            session_id=session.conversation_id,
                        )
                    )
                    logger.info(
                        f"[INTERPRETATION] LLM interpretation complete, "
                        f"length: {len(interpretation)}"
                    )
                except Exception as e:
                    logger.error(
                        f"[INTERPRETATION] Failed to interpret command results: {e}"
                    )

            # NOTE: Output already appears naturally in PTY terminal (executed in shell)
            # No need to write it back - user and agent work as one in the same terminal
            # LLM interpretation appears in chat UI (not terminal)

            # Add to command history
            session.command_history.append(
                {
                    "command": command,
                    "risk": risk.value,
                    "timestamp": time.time(),
                    "auto_approved": True,
                    "result": result,
                }
            )

            session.last_activity = time.time()

            # Broadcast pre-approval status update to WebSocket clients
            await self._broadcast_approval_status(
                session,
                command=command,
                approved=True,
                comment=f"Auto-approved ({risk.value} risk)",
                pre_approved=True,
            )

            # Add approval metadata to result for UI display
            result["approval_status"] = "pre_approved"
            result["approval_comment"] = f"Auto-approved ({risk.value} risk)"
            result["command"] = command

            return result

        except Exception as e:
            logger.error(f"Command execution error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "command": command,
            }

    async def approve_command(
        self,
        session_id: str,
        approved: bool,
        user_id: Optional[str] = None,
        comment: Optional[str] = None,
        auto_approve_future: bool = False,
    ) -> Dict[str, Any]:
        """
        Approve or deny a pending agent command.

        Args:
            session_id: Agent session ID
            approved: Whether command is approved
            user_id: User who made the decision
            comment: Optional comment or reason for the decision
            auto_approve_future: Auto-approve similar commands in the future

        Returns:
            Result of approval decision
        """
        # CRITICAL: Get per-session lock to prevent race conditions
        # This ensures only one approval operation per session at a time
        approval_lock = await self._get_approval_lock(session_id)
        async with approval_lock:
            return await self._approve_command_internal(
                session_id, approved, user_id, comment, auto_approve_future
            )

    async def _approve_command_internal(
        self,
        session_id: str,
        approved: bool,
        user_id: Optional[str] = None,
        comment: Optional[str] = None,
        auto_approve_future: bool = False,
    ) -> Dict[str, Any]:
        """Internal implementation of approve_command (called with lock held)."""
        session = await self.get_session(session_id)
        if not session:
            logger.error(f"approve_command: Session {session_id} not found")
            logger.error(
                f"approve_command: Available sessions: {list(self.sessions.keys())}"
            )
            return {
                "status": "error",
                "error": "Session not found",
            }

        logger.info(
            f"🎯 [APPROVAL RECEIVED] Session: {session_id}, Approved: {approved}, "
            f"Pending: {session.pending_approval is not None}, Comment: {comment}"
        )
        logger.info(
            f"🎯 [APPROVAL RECEIVED] Session state: {session.state.value}, "
            f"Agent ID: {session.agent_id}, Conversation ID: {session.conversation_id}"
        )
        logger.info(
            f"🎯 [APPROVAL RECEIVED] Pending approval: {session.pending_approval}"
        )

        if not session.pending_approval:
            logger.warning(
                f"approve_command: No pending approval for session {session_id}. "
                f"State: {session.state.value}, "
                f"command_history: {len(session.command_history)} commands"
            )
            return {
                "status": "error",
                "error": "No pending approval",
            }

        command = session.pending_approval.get("command")
        risk_level = session.pending_approval.get("risk")  # Save before clearing
        command_id = session.pending_approval.get(
            "command_id"
        )  # Get command_id from pending approval

        if approved:
            # REUSABLE PRINCIPLE: Update command state in queue
            if command_id:
                await self.command_queue.approve_command(
                    command_id=command_id,
                    user_id=user_id or "web_user",
                    comment=comment,
                )
                logger.info(
                    f"✅ [QUEUE] Command {command_id} approved in queue by {user_id or 'web_user'}"
                )

            # Execute approved command
            try:
                # Log approval
                if session.conversation_id:
                    await self.terminal_logger.log_command(
                        session_id=session.conversation_id,
                        command=command,
                        run_type="manual",  # User approved, treat as manual
                        status="approved",
                        user_id=user_id,
                    )

                # REUSABLE PRINCIPLE: Mark execution start in queue
                if command_id:
                    await self.command_queue.start_execution(command_id)
                    logger.info(
                        f"✅ [QUEUE] Command {command_id} marked as EXECUTING in queue"
                    )

                # CRITICAL: Execute in PTY (true collaboration mode - works on any host)
                # User and agent work as one in the same terminal
                result = await self._execute_in_pty(session, command)

                # CRITICAL FIX: Poll chat history for output (event-driven, no fixed timeout)
                # WebSocket handler saves output to chat asynchronously - poll until it appears
                if session.conversation_id:
                    try:
                        logger.info(
                            "[OUTPUT FETCH] Polling chat history for terminal output..."
                        )

                        # Poll chat history until output appears (max 10 seconds)
                        max_attempts = 50  # 50 attempts * 200ms = 10 seconds max
                        attempt = 0
                        terminal_output = ""

                        while attempt < max_attempts and not terminal_output:
                            # Fetch recent messages from chat
                            recent_messages = (
                                await self.chat_history_manager.get_session_messages(
                                    session_id=session.conversation_id,
                                    limit=10,  # Get last 10 messages
                                )
                            )

                            # Search for most recent terminal_output message
                            for msg in reversed(recent_messages):
                                if msg.get("message_type") == "terminal_output":
                                    terminal_output = msg.get("text", "")
                                    elapsed_ms = attempt * 200
                                    logger.info(
                                        f"[OUTPUT FETCH] ✅ Found terminal output "
                                        f"after {elapsed_ms}ms: "
                                        f"{len(terminal_output)} chars"
                                    )
                                    break

                            if not terminal_output:
                                await asyncio.sleep(
                                    0.2
                                )  # 200ms between polling attempts
                                attempt += 1

                        # Populate result with the output from chat
                        if terminal_output:
                            result["stdout"] = terminal_output
                            logger.info(
                                f"[OUTPUT FETCH] Populated result[stdout] with "
                                f"{len(terminal_output)} chars"
                            )
                        else:
                            logger.warning(
                                f"[OUTPUT FETCH] No terminal output found after "
                                f"{max_attempts * 200}ms "
                                f"({max_attempts} attempts)"
                            )

                    except Exception as e:
                        logger.error(
                            f"[OUTPUT FETCH] Failed to poll chat history for output: {e}"
                        )

                # REUSABLE PRINCIPLE: Write output to queue (single source of truth)
                if command_id:
                    await self.command_queue.complete_command(
                        command_id=command_id,
                        output=result.get("stdout", ""),
                        stderr=result.get("stderr", ""),
                        return_code=result.get("return_code", 0),
                    )
                    logger.info(
                        f"✅ [QUEUE] Command {command_id} completed in queue: "
                        f"stdout={len(result.get('stdout', ''))} chars, "
                        f"stderr={len(result.get('stderr', ''))} chars, "
                        f"return_code={result.get('return_code', 0)}"
                    )

                # Log command execution result
                if session.conversation_id:
                    await self.terminal_logger.log_command(
                        session_id=session.conversation_id,
                        command=command,
                        run_type="manual",
                        status=(
                            "success" if result.get("status") == "success" else "error"
                        ),
                        result=result,
                        user_id=user_id,
                    )

                # Save command and output to chat history
                await self._save_command_to_chat(
                    session.conversation_id, command, result, command_type="approved"
                )

                # CRITICAL FIX: Call LLM to interpret command results
                if session.conversation_id:
                    try:
                        logger.info(
                            f"[INTERPRETATION] Starting LLM interpretation "
                            f"for approved command: {command}"
                        ),
                        interpretation = (
                            await self.chat_workflow_manager.interpret_terminal_command(
                                command=command,
                                stdout=result.get("stdout", ""),
                                stderr=result.get("stderr", ""),
                                return_code=result.get("return_code", 0),
                                session_id=session.conversation_id,
                            )
                        )
                        logger.info(
                            f"[INTERPRETATION] LLM interpretation complete, "
                        f"length: {len(interpretation)}"
                        )
                    except Exception as e:
                        logger.error(
                            f"[INTERPRETATION] Failed to interpret approved command results: {e}"
                        )

                # NOTE: Output already appears naturally in PTY terminal (executed in shell)
                # No need to write it back - user and agent work as one in the same terminal
                # LLM interpretation appears in chat UI (not terminal)

                # Add to command history
                session.command_history.append(
                    {
                        "command": command,
                        "risk": risk_level,
                        "timestamp": time.time(),
                        "approved_by": user_id,
                        "approval_comment": comment,
                        "result": result,
                    }
                )

                session.pending_approval = None
                session.state = AgentSessionState.AGENT_CONTROL
                session.last_activity = time.time()

                logger.info(
                    f"✅ [APPROVAL EXECUTED] Command approved and executed: {command}"
                    + (f" with comment: {comment}" if comment else "")
                )
                logger.info(
                    f"✅ [APPROVAL EXECUTED] Session {session_id} updated: "
                    f"pending_approval=None, state=AGENT_CONTROL, "
                    f"command_history length={len(session.command_history)}"
                )

                # Store auto-approve rule if requested
                if auto_approve_future and user_id:
                    await self._store_auto_approve_rule(
                        user_id=user_id,
                        command=command,
                        risk_level=risk_level,
                    )

                # CRITICAL FIX: Update chat message metadata to persist approval status
                # This prevents the approval UI from reverting to "pending" when frontend polls
                if session.conversation_id:
                    try:
                        updated = (
                            await self.chat_history_manager.update_message_metadata(
                                session_id=session.conversation_id,
                                metadata_filter={
                                    "terminal_session_id": session_id,
                                    "requires_approval": True,
                                },
                                metadata_updates={
                                    "approval_status": "approved",
                                    "approval_comment": comment,
                                    "approved_by": user_id,
                                    "approved_at": time.time(),
                                },
                            )
                        )
                        if updated:
                            logger.info(
                                f"✅ Updated chat message with approval status: "
                                f"session={session.conversation_id}, terminal_session={session_id}"
                            )
                        else:
                            logger.warning(
                                f"⚠️ Could not find chat message to update approval status: "
                                f"session={session.conversation_id}, terminal_session={session_id}"
                            )
                    except Exception as metadata_update_error:
                        logger.error(
                            f"Failed to update chat message metadata (non-fatal): "
                            f"{metadata_update_error}",
                            exc_info=True,
                        )

                    # CRITICAL FIX: Add approval response message to chat history
                    # This ensures _restore_pending_approval sees "approved" keyword
                    # and doesn't restore
                    try:
                        await self.chat_history_manager.add_message(
                            session_id=session.conversation_id,
                            role="system",
                            text=f"✅ Command approved and executed: `{command}`"
                            + (f" - {comment}" if comment else ""),
                            message_type="command_approval_response",
                            metadata={
                                "command": command,
                                "terminal_session_id": session_id,
                                "approval_status": "approved",
                                "approved_by": user_id,
                                "approved_at": time.time(),
                            },
                        )
                        logger.info(
                            f"✅ [CHAT MESSAGE] Added command_approval_response to chat history: "
                            f"command={command}, status=approved"
                        )
                    except Exception as chat_msg_error:
                        logger.error(
                            f"Failed to add approval response to chat history: {chat_msg_error}",
                            exc_info=True,
                        )

                # Broadcast approval status update to WebSocket clients
                await self._broadcast_approval_status(
                    session,
                    command=command,
                    approved=True,
                    comment=comment,
                )

                return {
                    "status": "approved",
                    "command": command,
                    "result": result,
                    "comment": comment,
                    "auto_approve_stored": auto_approve_future,
                }

            except Exception as e:
                logger.error(f"Approved command execution error: {e}")
                return {
                    "status": "error",
                    "error": str(e),
                    "command": command,
                }
        else:
            # Command denied
            # REUSABLE PRINCIPLE: Update command state in queue
            if command_id:
                await self.command_queue.deny_command(
                    command_id=command_id,
                    user_id=user_id or "web_user",
                    comment=comment,
                )
                logger.info(
                    f"✅ [QUEUE] Command {command_id} denied in queue by {user_id or 'web_user'}"
                )

            logger.info(
                f"Command denied by user: {command}"
                + (f" with reason: {comment}" if comment else "")
            )

            # Track if denial message was saved (for avoiding duplicate messages)
            denial_message_saved = False

            # Log denial
            if session.conversation_id:
                await self.terminal_logger.log_command(
                    session_id=session.conversation_id,
                    command=command,
                    run_type="manual",
                    status="denied",
                    user_id=user_id,
                )

                # CRITICAL: Save denial with user's alternative suggestion to chat
                # This allows the agent to see the feedback and propose a different approach
                # Also ensures _restore_pending_approval sees "denied" keyword and doesn't restore
                if comment:
                    try:
                        await self.chat_history_manager.add_message(
                            sender="user",
                            text=(
                                f"❌ Command denied: `{command}`\n\n"
                                f"💡 **Alternative approach suggested:**\n{comment}"
                            ),
                            message_type="command_denial",
                            session_id=session.conversation_id,
                            metadata={
                                "command": command,
                                "terminal_session_id": session.session_id,
                                "approval_status": "denied",
                                "denied_by": user_id,
                                "denied_at": time.time(),
                                "alternative_suggestion": comment,
                            },
                        ),
                        denial_message_saved = True
                        logger.info(
                            f"✅ [DENIAL FEEDBACK] Saved user's alternative "
                            f"suggestion to chat: {comment[:50]}..."
                        )
                    except Exception as e:
                        logger.error(f"Failed to save denial feedback to chat: {e}")

            # Add to command history (for audit trail)
            session.command_history.append(
                {
                    "command": command,
                    "risk": session.pending_approval.get("risk"),
                    "timestamp": time.time(),
                    "denied_by": user_id,
                    "denial_reason": comment,
                    "result": {"status": "denied_by_user"},
                }
            )

            session.pending_approval = None
            session.state = AgentSessionState.AGENT_CONTROL

            # CRITICAL FIX: Update chat message metadata to persist denial status
            # This prevents the approval UI from reverting to "pending" when frontend polls
            if session.conversation_id:
                try:
                    updated = await self.chat_history_manager.update_message_metadata(
                        session_id=session.conversation_id,
                        metadata_filter={
                            "terminal_session_id": session_id,
                            "requires_approval": True,
                        },
                        metadata_updates={
                            "approval_status": "denied",
                            "approval_comment": comment,
                            "denied_by": user_id,
                            "denied_at": time.time(),
                        },
                    )
                    if updated:
                        logger.info(
                            f"✅ Updated chat message with denial status: "
                            f"session={session.conversation_id}, terminal_session={session_id}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Could not find chat message to update denial status: "
                            f"session={session.conversation_id}, terminal_session={session_id}"
                        )
                except Exception as metadata_update_error:
                    logger.error(
                        f"Failed to update chat message metadata (non-fatal): "
                        f"{metadata_update_error}",
                        exc_info=True,
                    )

                # CRITICAL FIX: Add denial response message if not already saved above
                # This ensures _restore_pending_approval sees "denied" keyword and doesn't restore
                # Skip if already saved with user's alternative suggestion (has "denied" keyword)
                if not denial_message_saved:
                    try:
                        await self.chat_history_manager.add_message(
                            session_id=session.conversation_id,
                            role="system",
                            text=f"❌ Command denied: `{command}`",
                            message_type="command_approval_response",
                            metadata={
                                "command": command,
                                "terminal_session_id": session_id,
                                "approval_status": "denied",
                                "denied_by": user_id,
                                "denied_at": time.time(),
                            },
                        )
                        logger.info(
                            f"✅ [CHAT MESSAGE] Added command_approval_response to chat history: "
                            f"command={command}, status=denied"
                        )
                    except Exception as chat_msg_error:
                        logger.error(
                            f"Failed to add denial response to chat history: {chat_msg_error}",
                            exc_info=True,
                        )

            # Broadcast denial status update to WebSocket clients
            await self._broadcast_approval_status(
                session,
                command=command,
                approved=False,
                comment=comment,
            )

            return {
                "status": "denied",
                "command": command,
                "message": "Command execution denied by user",
                "comment": comment,
            }

    async def user_interrupt(
        self,
        session_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        User requests to interrupt agent and take control.

        Args:
            session_id: Agent session to interrupt
            user_id: User requesting control

        Returns:
            Result of interrupt request
        """
        session = await self.get_session(session_id)
        if not session:
            return {
                "status": "error",
                "error": "Session not found",
            }

        # Transition to user control
        previous_state = session.state
        session.state = AgentSessionState.USER_CONTROL

        logger.info(
            f"User {user_id} interrupted agent session {session_id} "
            f"(previous state: {previous_state.value})"
        )

        return {
            "status": "success",
            "message": "Agent interrupted, user has control",
            "previous_state": previous_state.value,
            "current_state": session.state.value,
            "pending_approval": session.pending_approval,
        }

    async def agent_resume(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Resume agent control after user interrupt.

        Args:
            session_id: Session to resume

        Returns:
            Result of resume request
        """
        session = await self.get_session(session_id)
        if not session:
            return {
                "status": "error",
                "error": "Session not found",
            }

        if session.state != AgentSessionState.USER_CONTROL:
            return {
                "status": "error",
                "error": f"Cannot resume from state: {session.state.value}",
            }

        session.state = AgentSessionState.AGENT_CONTROL

        logger.info(f"Agent resumed control of session {session_id}")

        return {
            "status": "success",
            "message": "Agent control resumed",
            "current_state": session.state.value,
        }

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive session information.

        Args:
            session_id: Session to retrieve

        Returns:
            Session information dictionary
        """
        session = await self.get_session(session_id)
        if not session:
            return None

        # Check if PTY session is alive
        pty_alive = False
        if session.pty_session_id:
            try:
                from backend.services.simple_pty import simple_pty_manager

                pty = simple_pty_manager.get_session(session.pty_session_id)
                pty_alive = pty is not None and pty.is_alive()
            except Exception as e:
                logger.error(f"Error checking PTY alive status: {e}")
                pty_alive = False

        return {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "agent_role": session.agent_role.value,
            "conversation_id": session.conversation_id,
            "host": session.host,
            "state": session.state.value,
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "uptime": time.time() - session.created_at,
            "command_count": len(session.command_history),
            "pending_approval": session.pending_approval,
            "metadata": session.metadata,
            "pty_alive": (
                pty_alive
            ),  # CRITICAL FIX: Add pty_alive to prevent auto-recreation
        }

    async def _store_auto_approve_rule(
        self,
        user_id: str,
        command: str,
        risk_level: str,
    ):
        """
        Store an auto-approve rule for future similar commands.

        REFACTORED: Now uses CommandApprovalManager for reusability.

        Args:
            user_id: User who created the rule
            command: Command that was approved
            risk_level: Risk level of the command
        """
        await self.approval_manager.store_auto_approve_rule(
            user_id=user_id,
            command=command,
            risk_level=risk_level,
        )

    async def _check_auto_approve_rules(
        self,
        user_id: str,
        command: str,
        risk_level: str,
    ) -> bool:
        """
        Check if command matches any auto-approve rules.

        REFACTORED: Now uses CommandApprovalManager for reusability.

        Args:
            user_id: User ID to check rules for
            command: Command to check
            risk_level: Risk level of the command

        Returns:
            True if command should be auto-approved
        """
        return await self.approval_manager.check_auto_approve_rules(
            user_id=user_id,
            command=command,
            risk_level=risk_level,
        )

    async def _broadcast_approval_status(
        self,
        session: AgentTerminalSession,
        command: str,
        approved: bool,
        comment: Optional[str] = None,
        pre_approved: bool = False,
    ):
        """
        Broadcast approval status update to WebSocket clients.

        This updates the chat message metadata to show approval/denial status
        in the UI with color-coded visual indicators:
        - pre_approved (blue): Auto-approved by security policy
        - approved (green): User manually approved
        - denied (red): User manually denied

        Args:
            session: Agent terminal session
            command: Command that was approved/denied
            approved: Whether command was approved
            comment: Optional comment from user
            pre_approved: Whether this was auto-approved by security policy
        """
        try:
            # Only broadcast if there's a linked conversation
            if not session.conversation_id:
                logger.debug("No conversation_id - skipping WebSocket broadcast")
                return

            # Determine status based on approval type
            if pre_approved:
                status = "pre_approved"
            elif approved:
                status = "approved"
            else:
                status = "denied"

            # IMPLEMENTED: Real-time WebSocket broadcasting via event_manager
            try:
                from src.event_manager import event_manager

                await event_manager.publish(
                    event_type="command_approval_status",
                    payload={
                        "conversation_id": session.conversation_id,
                        "terminal_session_id": session.session_id,
                        "command": command,
                        "status": status,
                        "approved": approved,
                        "comment": comment,
                        "pre_approved": pre_approved,
                    },
                )
                logger.info(
                    f"✅ Approval status broadcast sent: "
                    f"conversation_id={session.conversation_id}, "
                    f"status={status}, "
                    f"command={command}, "
                    f"comment={comment}"
                )
            except Exception as broadcast_error:
                logger.warning(
                    f"Failed to broadcast approval status (non-fatal): {broadcast_error}"
                )
                # Continue - don't fail the approval process if broadcast fails

        except Exception as e:
            logger.error(f"Error in approval status update: {e}", exc_info=True)
            # Don't fail the approval process if broadcast fails
