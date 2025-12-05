# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Terminal Service

Main service class that composes all agent terminal functionality.
"""

import logging
import time
from typing import Optional

from backend.models.command_execution import CommandState
from backend.services.command_approval_manager import AgentRole, CommandApprovalManager
from backend.services.command_execution_queue import get_command_queue
from backend.type_defs.common import Metadata
from src.chat_history import ChatHistoryManager
from src.logging.terminal_logger import TerminalLogger
from src.monitoring.prometheus_metrics import get_metrics_manager
from src.secure_command_executor import SecureCommandExecutor, SecurityPolicy

from .approval_handler import ApprovalHandler
from .command_executor import CommandExecutor
from .models import AgentSessionState, AgentTerminalSession
from .session_manager import SessionManager
from .utils import create_command_execution, is_interactive_command

logger = logging.getLogger(__name__)


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

        Args:
            redis_client: Redis client for session persistence
            chat_workflow_manager: Existing ChatWorkflowManager instance
            command_queue: Command execution queue (default: singleton instance)
        """
        self.redis_client = redis_client
        self.security_policy = SecurityPolicy()

        # Initialize ChatHistoryManager for chat integration
        self.chat_history_manager = ChatHistoryManager()

        # Use passed ChatWorkflowManager instead of creating new one
        self.chat_workflow_manager = chat_workflow_manager

        # Initialize managers
        self.approval_manager = CommandApprovalManager()
        self.command_queue = command_queue or get_command_queue()

        # Terminal command logger
        self.terminal_logger = TerminalLogger(
            redis_client=redis_client, data_dir="data/chats"
        )

        # Prometheus metrics instance
        self.prometheus_metrics = get_metrics_manager()

        # Initialize component modules
        self.session_manager = SessionManager(
            redis_client=redis_client, chat_history_manager=self.chat_history_manager
        )
        self.command_executor = CommandExecutor(
            chat_history_manager=self.chat_history_manager
        )
        self.approval_handler = ApprovalHandler(
            approval_manager=self.approval_manager,
            chat_history_manager=self.chat_history_manager,
            command_queue=self.command_queue,
        )

        logger.info(
            "AgentTerminalService initialized with security controls and command queue"
        )

    # ============================================================================
    # Session Management (delegated to SessionManager)
    # ============================================================================

    async def create_session(
        self,
        agent_id: str,
        agent_role: AgentRole,
        conversation_id: Optional[str] = None,
        host: str = "main",
        metadata: Optional[Metadata] = None,
    ) -> AgentTerminalSession:
        """Create a new agent terminal session with PTY integration."""
        return await self.session_manager.create_session(
            agent_id=agent_id,
            agent_role=agent_role,
            conversation_id=conversation_id,
            host=host,
            metadata=metadata,
        )

    async def get_session(self, session_id: str) -> Optional[AgentTerminalSession]:
        """Get session by ID."""
        return await self.session_manager.get_session(session_id)

    async def list_sessions(
        self,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> list[AgentTerminalSession]:
        """List agent terminal sessions."""
        return await self.session_manager.list_sessions(
            agent_id=agent_id, conversation_id=conversation_id
        )

    async def close_session(self, session_id: str) -> bool:
        """Close an agent terminal session."""
        # Clean up approval lock
        await self.approval_handler.cleanup_approval_lock(session_id)
        return await self.session_manager.close_session(session_id)

    async def get_session_info(self, session_id: str) -> Optional[Metadata]:
        """Get comprehensive session information."""
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
            "pty_alive": pty_alive,
        }

    # ============================================================================
    # Command Execution (delegated to CommandExecutor)
    # ============================================================================

    async def execute_command(
        self,
        session_id: str,
        command: str,
        description: Optional[str] = None,
        force_approval: bool = False,
    ) -> Metadata:
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

        # Create secure command executor
        executor = SecureCommandExecutor(
            policy=self.security_policy,
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
        allowed, permission_reason = self.approval_handler.check_agent_permission(
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

        # CRITICAL: Force ALL commands through approval workflow
        needs_approval = True

        if needs_approval:
            # Check auto-approve rules
            user_id = session.conversation_id or "default_user"
            is_auto_approved = await self.approval_handler.check_auto_approve_rules(
                user_id=user_id,
                command=command,
                risk_level=risk.value,
            )

            if is_auto_approved:
                logger.info(
                    f"Command auto-approved by rule: {command} "
                    f"(user: {user_id}, risk: {risk.value})"
                )
                # Fall through to execute command below
            else:
                # Create CommandExecution and add to queue
                cmd_execution = create_command_execution(
                    session=session,
                    command=command,
                    description=description,
                    risk=risk,
                    risk_reasons=reasons,
                    is_interactive=is_interactive,
                    interactive_reasons=interactive_reasons,
                )

                await self.command_queue.add_command(cmd_execution)
                logger.info(
                    f"✅ [QUEUE] Added command {cmd_execution.command_id} to queue"
                )

                # Store pending approval in session
                session.pending_approval = {
                    "command": command,
                    "description": description,
                    "risk": risk.value,
                    "reasons": reasons,
                    "timestamp": time.time(),
                    "command_id": cmd_execution.command_id,
                    "is_interactive": is_interactive,
                    "interactive_reasons": interactive_reasons,
                }

                # Persist session to Redis
                if self.redis_client:
                    await self.session_manager._persist_session(session)

                # Log pending approval
                if session.conversation_id:
                    await self.terminal_logger.log_command(
                        session_id=session.conversation_id,
                        command=command,
                        run_type="autobot",
                        status="pending_approval",
                        user_id=user_id,
                    )

                    # NOTE: Approval request chat message is persisted by ChatWorkflowManager
                    # via ToolHandlerMixin._persist_approval_request() to avoid duplication.
                    # Issue #343: Removed duplicate persistence that caused 21x message duplication.

                return {
                    "status": "pending_approval",
                    "command": command,
                    "risk": risk.value,
                    "reasons": reasons,
                    "description": description,
                    "agent_role": session.agent_role.value,
                    "approval_required": True,
                    "command_id": cmd_execution.command_id,
                    "terminal_session_id": cmd_execution.terminal_session_id,
                    "is_interactive": is_interactive,
                    "interactive_reasons": interactive_reasons,
                }

        # Execute command (auto-approved)
        try:
            task_start_time = time.time()

            # Log execution start
            if session.conversation_id:
                await self.terminal_logger.log_command(
                    session_id=session.conversation_id,
                    command=command,
                    run_type="autobot",
                    status="executing",
                    user_id=None,
                )

            # Execute in PTY
            result = await self.command_executor.execute_in_pty(session, command)

            # Record Prometheus metrics
            task_duration = time.time() - task_start_time
            status = "success" if result.get("status") == "success" else "error"
            self.prometheus_metrics.record_task_execution(
                task_type="command_execution",
                agent_type=session.agent_role.value,
                status=status,
                duration=task_duration,
            )

            # Log result
            if session.conversation_id:
                await self.terminal_logger.log_command(
                    session_id=session.conversation_id,
                    command=command,
                    run_type="autobot",
                    status=status,
                    result=result,
                    user_id=None,
                )

            # Save to chat history
            await self._save_command_to_chat(
                session.conversation_id, command, result, command_type="agent"
            )

            # Call LLM to interpret results
            if session.conversation_id and self.chat_workflow_manager:
                try:
                    logger.info(
                        f"[INTERPRETATION] Starting LLM interpretation for command: {command}"
                    )
                    await self.chat_workflow_manager.interpret_terminal_command(
                        command=command,
                        stdout=result.get("stdout", ""),
                        stderr=result.get("stderr", ""),
                        return_code=result.get("return_code", 0),
                        session_id=session.conversation_id,
                    )
                except Exception as e:
                    logger.error(f"[INTERPRETATION] Failed to interpret results: {e}")

            # Add to history
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

            # Broadcast approval status
            await self.approval_handler.broadcast_approval_status(
                session,
                command=command,
                approved=True,
                comment=f"Auto-approved ({risk.value} risk)",
                pre_approved=True,
            )

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

    async def _save_command_to_chat(
        self,
        conversation_id: str,
        command: str,
        result: dict,
        command_type: str = "agent",
    ):
        """Save command and output to chat history."""
        if not conversation_id:
            return

        try:
            # Save command
            await self.chat_history_manager.add_message(
                sender="agent_terminal",
                text=f"$ {command}",
                message_type="terminal_command",
                session_id=conversation_id,
            )

            # Save output (if any)
            if result.get("stdout") or result.get("stderr"):
                output_text = (
                    result.get("stdout", "") + result.get("stderr", "")
                ).strip()
                if output_text:
                    # Strip ANSI escape codes
                    from src.utils.encoding_utils import strip_ansi_codes

                    clean_output = strip_ansi_codes(output_text).strip()
                    if clean_output:
                        await self.chat_history_manager.add_message(
                            sender="agent_terminal",
                            text=clean_output,
                            message_type="terminal_output",
                            session_id=conversation_id,
                        )

            logger.info(
                f"[CHAT INTEGRATION] {command_type.capitalize()} command saved to chat"
            )
        except Exception as e:
            logger.error(f"Failed to save {command_type} command to chat: {e}")

    # ============================================================================
    # Approval Workflow (delegated to ApprovalHandler)
    # ============================================================================

    async def approve_command(
        self,
        session_id: str,
        approved: bool,
        user_id: Optional[str] = None,
        comment: Optional[str] = None,
        auto_approve_future: bool = False,
    ) -> Metadata:
        """Approve or deny a pending agent command."""
        # Get per-session lock
        approval_lock = await self.approval_handler._get_approval_lock(session_id)
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
    ) -> Metadata:
        """Internal implementation of approve_command."""
        session = await self.get_session(session_id)
        if not session:
            return {"status": "error", "error": "Session not found"}

        if not session.pending_approval:
            return {"status": "error", "error": "No pending approval"}

        command = session.pending_approval.get("command")
        risk_level = session.pending_approval.get("risk")
        command_id = session.pending_approval.get("command_id")

        if approved:
            # Update queue status
            await self.approval_handler.update_command_queue_status(
                command_id=command_id,
                approved=True,
                user_id=user_id,
                comment=comment,
            )

            try:
                # Log approval
                if session.conversation_id:
                    await self.terminal_logger.log_command(
                        session_id=session.conversation_id,
                        command=command,
                        run_type="manual",
                        status="approved",
                        user_id=user_id,
                    )

                # Execute command
                result = await self.command_executor.execute_in_pty(session, command)

                # Update queue with results
                await self.approval_handler.update_command_queue_status(
                    command_id=command_id,
                    approved=True,
                    output=result.get("stdout", ""),
                    stderr=result.get("stderr", ""),
                    return_code=result.get("return_code", 0),
                )

                # Log result
                if session.conversation_id:
                    await self.terminal_logger.log_command(
                        session_id=session.conversation_id,
                        command=command,
                        run_type="manual",
                        status="success" if result.get("status") == "success" else "error",
                        result=result,
                        user_id=user_id,
                    )

                # Save to chat
                await self._save_command_to_chat(
                    session.conversation_id, command, result, command_type="approved"
                )

                # Interpret results
                if session.conversation_id and self.chat_workflow_manager:
                    try:
                        await self.chat_workflow_manager.interpret_terminal_command(
                            command=command,
                            stdout=result.get("stdout", ""),
                            stderr=result.get("stderr", ""),
                            return_code=result.get("return_code", 0),
                            session_id=session.conversation_id,
                        )
                    except Exception as e:
                        logger.error(f"Failed to interpret approved command results: {e}")

                # Add to history
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

                # Store auto-approve rule
                if auto_approve_future and user_id:
                    await self.approval_handler.store_auto_approve_rule(
                        user_id=user_id,
                        command=command,
                        risk_level=risk_level,
                    )

                # Update chat status
                await self.approval_handler.update_chat_approval_status(
                    session=session,
                    command=command,
                    approved=True,
                    user_id=user_id,
                    comment=comment,
                )

                # Broadcast status
                await self.approval_handler.broadcast_approval_status(
                    session, command=command, approved=True, comment=comment
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
            await self.approval_handler.update_command_queue_status(
                command_id=command_id,
                approved=False,
                user_id=user_id,
                comment=comment,
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

            # Add to history
            session.command_history.append(
                {
                    "command": command,
                    "risk": risk_level,
                    "timestamp": time.time(),
                    "denied_by": user_id,
                    "denial_reason": comment,
                    "result": {"status": "denied_by_user"},
                }
            )

            session.pending_approval = None
            session.state = AgentSessionState.AGENT_CONTROL

            # Update chat status
            await self.approval_handler.update_chat_approval_status(
                session=session,
                command=command,
                approved=False,
                user_id=user_id,
                comment=comment,
            )

            # Broadcast status
            await self.approval_handler.broadcast_approval_status(
                session, command=command, approved=False, comment=comment
            )

            return {
                "status": "denied",
                "command": command,
                "message": "Command execution denied by user",
                "comment": comment,
            }

    # ============================================================================
    # User Control Management
    # ============================================================================

    async def user_interrupt(self, session_id: str, user_id: str) -> Metadata:
        """User requests to interrupt agent and take control."""
        session = await self.get_session(session_id)
        if not session:
            return {"status": "error", "error": "Session not found"}

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

    async def agent_resume(self, session_id: str) -> Metadata:
        """Resume agent control after user interrupt."""
        session = await self.get_session(session_id)
        if not session:
            return {"status": "error", "error": "Session not found"}

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
