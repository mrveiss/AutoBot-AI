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

from src.secure_command_executor import CommandRisk, SecureCommandExecutor, SecurityPolicy

logger = logging.getLogger(__name__)


class AgentSessionState(Enum):
    """State machine for agent terminal sessions"""
    AGENT_CONTROL = "agent_control"  # Agent executing commands
    USER_INTERRUPT = "user_interrupt"  # User requesting control
    USER_CONTROL = "user_control"  # User has control
    AGENT_RESUME = "agent_resume"  # Agent resuming after user


class AgentRole(Enum):
    """Agent roles with different privilege levels"""
    CHAT_AGENT = "chat_agent"  # Chat agents (lowest privilege)
    AUTOMATION_AGENT = "automation_agent"  # Workflow automation agents
    SYSTEM_AGENT = "system_agent"  # System monitoring agents
    ADMIN_AGENT = "admin_agent"  # Administrative agents (highest privilege)


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

    def __init__(self, redis_client=None):
        """
        Initialize agent terminal service.

        Args:
            redis_client: Redis client for session persistence
        """
        self.redis_client = redis_client
        self.sessions: Dict[str, AgentTerminalSession] = {}
        self.security_policy = SecurityPolicy()

        # Agent-specific security policy
        self.agent_permissions = {
            AgentRole.CHAT_AGENT: {
                "max_risk": CommandRisk.MODERATE,
                "auto_approve_safe": True,
                "auto_approve_moderate": False,  # Requires user approval
                "allow_high": False,
                "allow_dangerous": False,
            },
            AgentRole.AUTOMATION_AGENT: {
                "max_risk": CommandRisk.HIGH,
                "auto_approve_safe": True,
                "auto_approve_moderate": True,
                "allow_high": True,  # Requires approval
                "allow_dangerous": False,
            },
            AgentRole.SYSTEM_AGENT: {
                "max_risk": CommandRisk.HIGH,
                "auto_approve_safe": True,
                "auto_approve_moderate": True,
                "allow_high": True,  # Requires approval
                "allow_dangerous": False,
            },
            AgentRole.ADMIN_AGENT: {
                "max_risk": CommandRisk.CRITICAL,
                "auto_approve_safe": True,
                "auto_approve_moderate": True,
                "allow_high": True,  # Requires approval
                "allow_dangerous": True,  # ALWAYS requires approval
            },
        }

        logger.info("AgentTerminalService initialized with security controls")

    async def create_session(
        self,
        agent_id: str,
        agent_role: AgentRole,
        conversation_id: Optional[str] = None,
        host: str = "main",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentTerminalSession:
        """
        Create a new agent terminal session.

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

        session = AgentTerminalSession(
            session_id=session_id,
            agent_id=agent_id,
            agent_role=agent_role,
            conversation_id=conversation_id,
            host=host,
            metadata=metadata or {},
        )

        self.sessions[session_id] = session

        logger.info(
            f"Created agent terminal session {session_id} "
            f"for agent {agent_id} (role: {agent_role.value})"
        )

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
            }

            import json
            self.redis_client.setex(
                key,
                3600,  # 1 hour TTL
                json.dumps(session_data)
            )
        except Exception as e:
            logger.error(f"Failed to persist session to Redis: {e}")

    async def get_session(self, session_id: str) -> Optional[AgentTerminalSession]:
        """
        Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session if found, None otherwise
        """
        return self.sessions.get(session_id)

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
        if session_id in self.sessions:
            session = self.sessions[session_id]
            del self.sessions[session_id]

            logger.info(f"Closed agent terminal session {session_id}")

            # Remove from Redis
            if self.redis_client:
                try:
                    key = f"agent_terminal:session:{session_id}"
                    self.redis_client.delete(key)
                except Exception as e:
                    logger.error(f"Failed to remove session from Redis: {e}")

            return True

        return False

    def _check_agent_permission(
        self,
        agent_role: AgentRole,
        command_risk: CommandRisk,
    ) -> tuple[bool, str]:
        """
        Check if agent has permission to execute command at given risk level.

        Args:
            agent_role: Role of the agent
            command_risk: Risk level of the command

        Returns:
            Tuple of (allowed, reason)
        """
        permissions = self.agent_permissions.get(agent_role)
        if not permissions:
            return False, f"Unknown agent role: {agent_role}"

        # Check max risk level
        max_risk = permissions["max_risk"]

        # Map risk levels to numerical values for comparison
        risk_levels = {
            CommandRisk.SAFE: 0,
            CommandRisk.MODERATE: 1,
            CommandRisk.HIGH: 2,
            CommandRisk.CRITICAL: 3,
            CommandRisk.FORBIDDEN: 4,
        }

        if risk_levels.get(command_risk, 999) > risk_levels.get(max_risk, 0):
            return False, f"Command risk {command_risk.value} exceeds agent max risk {max_risk.value}"

        # Check specific risk permissions
        if command_risk == CommandRisk.HIGH and not permissions.get("allow_high"):
            return False, "Agent not permitted to execute HIGH risk commands"

        if command_risk == CommandRisk.CRITICAL and not permissions.get("allow_dangerous"):
            return False, "Agent not permitted to execute DANGEROUS commands"

        return True, "Permission granted"

    def _needs_approval(
        self,
        agent_role: AgentRole,
        command_risk: CommandRisk,
    ) -> bool:
        """
        Check if command needs user approval.

        Args:
            agent_role: Role of the agent
            command_risk: Risk level of the command

        Returns:
            True if approval is required
        """
        permissions = self.agent_permissions.get(agent_role, {})

        # SAFE commands can be auto-approved if permitted
        if command_risk == CommandRisk.SAFE:
            return not permissions.get("auto_approve_safe", False)

        # MODERATE commands need approval unless auto-approved
        if command_risk == CommandRisk.MODERATE:
            return not permissions.get("auto_approve_moderate", False)

        # HIGH and DANGEROUS always need approval
        return True

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

        # Check agent permissions
        allowed, permission_reason = self._check_agent_permission(session.agent_role, risk)
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
        needs_approval = self._needs_approval(session.agent_role, risk) or force_approval

        if needs_approval:
            # Store command in pending approval
            session.pending_approval = {
                "command": command,
                "description": description,
                "risk": risk.value,
                "reasons": reasons,
                "timestamp": time.time(),
            }

            logger.info(
                f"Command requires approval: {command} "
                f"(agent: {session.agent_id}, risk: {risk.value})"
            )

            return {
                "status": "pending_approval",
                "command": command,
                "risk": risk.value,
                "reasons": reasons,
                "description": description,
                "agent_role": session.agent_role.value,
                "approval_required": True,
            }

        # Execute command (auto-approved safe commands)
        try:
            result = await executor.run_shell_command(command, force_approval=False)

            # Add to command history
            session.command_history.append({
                "command": command,
                "risk": risk.value,
                "timestamp": time.time(),
                "result": result,
            })

            session.last_activity = time.time()

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
    ) -> Dict[str, Any]:
        """
        Approve or deny a pending agent command.

        Args:
            session_id: Agent session ID
            approved: Whether command is approved
            user_id: User who made the decision

        Returns:
            Result of approval decision
        """
        session = await self.get_session(session_id)
        if not session:
            return {
                "status": "error",
                "error": "Session not found",
            }

        if not session.pending_approval:
            return {
                "status": "error",
                "error": "No pending approval",
            }

        command = session.pending_approval.get("command")

        if approved:
            # Execute approved command
            executor = SecureCommandExecutor(
                policy=self.security_policy,
                use_docker_sandbox=False,
            )

            try:
                result = await executor.run_shell_command(command, force_approval=False)

                # Add to command history
                session.command_history.append({
                    "command": command,
                    "risk": session.pending_approval.get("risk"),
                    "timestamp": time.time(),
                    "approved_by": user_id,
                    "result": result,
                })

                session.pending_approval = None
                session.state = AgentSessionState.AGENT_CONTROL
                session.last_activity = time.time()

                logger.info(f"Command approved and executed: {command}")

                return {
                    "status": "approved",
                    "command": command,
                    "result": result,
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
            logger.info(f"Command denied by user: {command}")

            session.pending_approval = None
            session.state = AgentSessionState.AGENT_CONTROL

            return {
                "status": "denied",
                "command": command,
                "message": "Command execution denied by user",
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
        }
