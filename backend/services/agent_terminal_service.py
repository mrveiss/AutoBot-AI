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

from src.constants.network_constants import NetworkConstants
from src.constants.path_constants import PATH
from src.logging.terminal_logger import TerminalLogger
from src.chat_history_manager import ChatHistoryManager  # CRITICAL FIX: Chat integration
from src.chat_workflow_manager import ChatWorkflowManager  # For LLM interpretation
from src.secure_command_executor import (
    CommandRisk,
    SecureCommandExecutor,
    SecurityPolicy,
)
from backend.services.command_approval_manager import (
    AgentRole,
    CommandApprovalManager,
)

logger = logging.getLogger(__name__)


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

    def __init__(self, redis_client=None, chat_workflow_manager=None):
        """
        Initialize agent terminal service.

        Args:
            redis_client: Redis client for session persistence
            chat_workflow_manager: Existing ChatWorkflowManager instance (prevents circular initialization)
        """
        self.redis_client = redis_client
        self.sessions: Dict[str, AgentTerminalSession] = {}
        self.security_policy = SecurityPolicy()

        # Terminal command logger
        self.terminal_logger = TerminalLogger(
            redis_client=redis_client, data_dir="data/chats"
        )

        # CRITICAL FIX: Initialize ChatHistoryManager for chat integration
        self.chat_history_manager = ChatHistoryManager()

        # CRITICAL FIX: Use passed ChatWorkflowManager instead of creating new one (prevents circular loop)
        self.chat_workflow_manager = chat_workflow_manager

        # REFACTOR: Use CommandApprovalManager for reusable approval logic
        self.approval_manager = CommandApprovalManager()

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
                        f"PTY session {pty_session_id} exists but is dead (killed during restart). Recreating..."
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
                    )
                    pty_session_id = None
            else:
                logger.info(
                    f"Reusing existing ALIVE PTY session {pty_session_id} for agent terminal {session_id}"
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
                        f"Registered PTY session {pty_session_id} with conversation_id {conversation_id} for logging"
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

        self.sessions[session_id] = session

        logger.info(
            f"Created agent terminal session {session_id} "
            f"for agent {agent_id} (role: {agent_role.value}), "
            f"PTY session: {pty_session_id}"
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
                "pty_session_id": session.pty_session_id,  # CRITICAL: Store PTY session ID
                "pending_approval": session.pending_approval,  # CRITICAL: Persist pending approvals for page reload
            }

            import json

            # DEBUG: Log pending_approval before saving
            logger.warning(
                f"[PERSIST DEBUG] Session {session.session_id}: "
                f"pending_approval={session.pending_approval}"
            )

            json_data = json.dumps(session_data)
            await self.redis_client.setex(key, 3600, json_data)  # 1 hour TTL
            logger.debug(f"Persisted session {session.session_id} to Redis with key {key}")

            # DEBUG: Verify what was saved
            logger.warning(
                f"[PERSIST DEBUG] Saved to Redis: "
                f"pending_approval={session_data.get('pending_approval')}"
            )
        except Exception as e:
            logger.error(f"Failed to persist session to Redis: {e}")

    async def _save_command_to_chat(
        self, conversation_id: str, command: str, result: dict, command_type: str = "agent"
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
            logger.warning(f"[CHAT INTEGRATION] Saving {command_type} command to chat: {command[:50]}")

            # Save command
            await self.chat_history_manager.add_message(
                sender="agent_terminal",
                text=f"$ {command}",
                message_type="terminal_command",
                session_id=conversation_id,
            )

            # Save output (if any)
            logger.warning(f"[CHAT INTEGRATION] Result keys: {result.keys()}")
            logger.warning(f"[CHAT INTEGRATION] stdout: {result.get('stdout', 'MISSING')[:100]}")
            logger.warning(f"[CHAT INTEGRATION] stderr: {result.get('stderr', 'MISSING')[:100]}")
            if result.get("stdout") or result.get("stderr"):
                output_text = (result.get("stdout", "") + result.get("stderr", "")).strip()
                logger.warning(f"[CHAT INTEGRATION] Output text length: {len(output_text)}")
                if output_text:
                    await self.chat_history_manager.add_message(
                        sender="agent_terminal",
                        text=output_text,
                        message_type="terminal_output",
                        session_id=conversation_id,
                    )
                    logger.warning(f"[CHAT INTEGRATION] Output message saved successfully")
                else:
                    logger.warning(f"[CHAT INTEGRATION] Output text is empty after stripping")
            else:
                logger.warning(f"[CHAT INTEGRATION] No stdout or stderr in result")

            logger.warning(f"[CHAT INTEGRATION] {command_type.capitalize()} command saved to chat successfully")
        except Exception as e:
            logger.error(f"[EXCEPTION] Failed to save {command_type} command to chat: {e}")
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
        # Fast path: check in-memory sessions first
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
                    session.pending_approval = session_data.get("pending_approval")  # CRITICAL: Restore pending approvals

                    # Add back to memory cache
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
        logger.info(f"[PTY_WRITE] Called for session {session.session_id}, pty_session_id={session.pty_session_id}, text_len={len(text)}")

        if not session.pty_session_id:
            logger.warning("No PTY session ID available for writing")
            return False

        try:
            from backend.services.simple_pty import simple_pty_manager

            pty = simple_pty_manager.get_session(session.pty_session_id)
            logger.info(f"[PTY_WRITE] Got PTY session: {pty is not None}, alive: {pty.is_alive() if pty else 'N/A'}")

            # If PTY is not alive, recreate it (handles stale sessions after restart)
            if not pty or not pty.is_alive():
                logger.warning(
                    f"[PTY_WRITE] PTY session {session.pty_session_id} not alive (exists={pty is not None}), recreating..."
                )

                # Create new PTY with same session ID
                new_pty = simple_pty_manager.create_session(
                    session.pty_session_id,
                    initial_cwd=str(PATH.PROJECT_ROOT)
                )

                if new_pty:
                    logger.info(f"Recreated PTY session {session.pty_session_id}")
                    pty = new_pty
                else:
                    logger.error(f"Failed to recreate PTY session {session.pty_session_id}")
                    return False

            # Write to PTY
            success = pty.write_input(text)
            if success:
                logger.debug(
                    f"Wrote to PTY {session.pty_session_id}: {text[:50]}..."
                )
            return success

        except Exception as e:
            logger.error(f"Error writing to PTY: {e}")
            return False

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
        needs_approval = True  # Always require approval (auto-approve rules still apply)

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
                # Store command in pending approval
                session.pending_approval = {
                    "command": command,
                    "description": description,
                    "risk": risk.value,
                    "reasons": reasons,
                    "timestamp": time.time(),
                }

                # CRITICAL: Persist session to Redis so pending approval survives page reload
                if self.redis_client:
                    await self._persist_session(session)

                logger.info(
                    f"Command requires approval: {command} "
                    f"(agent: {session.agent_id}, risk: {risk.value})"
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
            # Log command execution start
            if session.conversation_id:
                await self.terminal_logger.log_command(
                    session_id=session.conversation_id,
                    command=command,
                    run_type="autobot",
                    status="executing",
                    user_id=None,
                )

            # Execute the command
            result = await executor.run_shell_command(command, force_approval=False)

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
                    logger.info(f"[INTERPRETATION] Starting LLM interpretation for command: {command}")
                    interpretation = await self.chat_workflow_manager.interpret_terminal_command(
                        command=command,
                        stdout=result.get("stdout", ""),
                        stderr=result.get("stderr", ""),
                        return_code=result.get("return_code", 0),
                        session_id=session.conversation_id,
                    )
                    logger.info(f"[INTERPRETATION] LLM interpretation complete, length: {len(interpretation)}")
                except Exception as e:
                    logger.error(f"[INTERPRETATION] Failed to interpret command results: {e}")

            # CRITICAL FIX: Write formatted command and output to PTY terminal for display
            # The command executes via subprocess (NOT in PTY shell), so we write
            # a formatted display to PTY for users to see it in the terminal tab.
            #
            # IMPORTANT: We write the OUTPUT, not the command itself, to prevent double execution.
            # Writing "command\n" would cause PTY shell to execute it again.

            # Format output for terminal display
            terminal_output = f"\r\n$ {command}\r\n"
            if result.get("stdout"):
                terminal_output += result["stdout"]
                if not result["stdout"].endswith("\n"):
                    terminal_output += "\r\n"
            if result.get("stderr"):
                terminal_output += result["stderr"]
                if not result["stderr"].endswith("\n"):
                    terminal_output += "\r\n"

            # Write formatted output to PTY (for terminal tab display)
            self._write_to_pty(session, terminal_output)

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
                f"approve_command: No pending approval for session {session_id}. State: {session.state.value}, command_history: {len(session.command_history)} commands"
            )
            return {
                "status": "error",
                "error": "No pending approval",
            }

        command = session.pending_approval.get("command")
        risk_level = session.pending_approval.get("risk")  # Save before clearing

        if approved:
            # Execute approved command
            # User has already approved, so callback always returns True
            async def pre_approved_callback(approval_data):
                return True

            executor = SecureCommandExecutor(
                policy=self.security_policy,
                require_approval_callback=pre_approved_callback,
                use_docker_sandbox=False,
            )

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

                # Execute the command
                result = await executor.run_shell_command(command, force_approval=False)

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
                        logger.info(f"[INTERPRETATION] Starting LLM interpretation for approved command: {command}")
                        interpretation = await self.chat_workflow_manager.interpret_terminal_command(
                            command=command,
                            stdout=result.get("stdout", ""),
                            stderr=result.get("stderr", ""),
                            return_code=result.get("return_code", 0),
                            session_id=session.conversation_id,
                        )
                        logger.info(f"[INTERPRETATION] LLM interpretation complete, length: {len(interpretation)}")
                    except Exception as e:
                        logger.error(f"[INTERPRETATION] Failed to interpret approved command results: {e}")

                # CRITICAL FIX: Write formatted command and output to PTY terminal for display
                # The command executes via subprocess (NOT in PTY shell), so we write
                # a formatted display to PTY for users to see it in the terminal tab.
                #
                # IMPORTANT: We write the OUTPUT, not the command itself, to prevent double execution.
                # Writing "command\n" would cause PTY shell to execute it again.

                # Format output for terminal display
                terminal_output = f"\r\n$ {command}\r\n"
                if result.get("stdout"):
                    terminal_output += result["stdout"]
                    if not result["stdout"].endswith("\n"):
                        terminal_output += "\r\n"
                if result.get("stderr"):
                    terminal_output += result["stderr"]
                    if not result["stderr"].endswith("\n"):
                        terminal_output += "\r\n"

                # Write formatted output to PTY (for terminal tab display)
                self._write_to_pty(session, terminal_output)

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
            logger.info(
                f"Command denied by user: {command}"
                + (f" with reason: {comment}" if comment else "")
            )

            # Log denial
            if session.conversation_id:
                await self.terminal_logger.log_command(
                    session_id=session.conversation_id,
                    command=command,
                    run_type="manual",
                    status="denied",
                    user_id=user_id,
                )

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
            "pty_alive": pty_alive,  # CRITICAL FIX: Add pty_alive to prevent auto-recreation
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

            # TODO: Implement WebSocket broadcasting for real-time UI updates
            # For now, log the approval status (will be picked up on next message/refresh)
            logger.info(
                f"Approval status update (WebSocket broadcast pending): "
                f"conversation_id={session.conversation_id}, "
                f"status={status}, "
                f"command={command}, "
                f"comment={comment}"
            )

            # Future implementation:
            # from backend.api.websockets import websocket_manager
            # await websocket_manager.broadcast_to_conversation(...)

        except Exception as e:
            logger.error(f"Error in approval status update: {e}", exc_info=True)
            # Don't fail the approval process if broadcast fails
