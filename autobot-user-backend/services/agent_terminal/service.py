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

from backend.services.command_approval_manager import AgentRole, CommandApprovalManager
from backend.services.command_execution_queue import get_command_queue
from backend.type_defs.common import Metadata
from chat_history import ChatHistoryManager
from logging.terminal_logger import TerminalLogger
from monitoring.prometheus_metrics import get_metrics_manager
from secure_command_executor import SecureCommandExecutor, SecurityPolicy

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
        if session.has_pty_session():
            try:
                from backend.services.simple_pty import simple_pty_manager

                pty = simple_pty_manager.get_session(session.pty_session_id)
                pty_alive = pty is not None and pty.is_alive()
            except Exception as e:
                logger.error("Error checking PTY alive status: %s", e)
                pty_alive = False

        # Issue #372: Use model method to reduce feature envy
        return session.to_info_dict(pty_alive=pty_alive)

    # ============================================================================
    # Helper Methods for execute_command (Issue #281)
    # ============================================================================

    def _validate_session_for_execution(
        self, session: Optional[AgentTerminalSession], session_id: str
    ) -> Optional[Metadata]:
        """Validate session exists and is not user-controlled (Issue #281: extracted)."""
        if not session:
            return {
                "status": "error",
                "error": "Session not found",
                "session_id": session_id,
            }

        if session.is_user_controlled():
            return session.get_blocked_error_response()

        return None

    def _assess_command(
        self, command: str
    ) -> tuple:
        """Assess command risk and interactivity (Issue #281: extracted)."""
        executor = SecureCommandExecutor(
            policy=self.security_policy,
            use_docker_sandbox=False,
        )

        risk, reasons = executor.assess_command_risk(command)
        is_interactive, interactive_reasons = is_interactive_command(command)

        if is_interactive:
            logger.info(
                f"Interactive command detected: {command} "
                f"(requires stdin: {', '.join(interactive_reasons)})"
            )

        return executor, risk, reasons, is_interactive, interactive_reasons

    async def _queue_command_for_approval(
        self,
        session: AgentTerminalSession,
        command: str,
        description: Optional[str],
        risk,
        reasons: list,
        is_interactive: bool,
        interactive_reasons: list,
    ) -> Metadata:
        """Queue command for user approval (Issue #281: extracted)."""
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
        logger.info("✅ [QUEUE] Added command %s to queue", cmd_execution.command_id)

        session.set_pending_approval(
            command=command,
            description=description,
            risk_value=risk.value,
            reasons=reasons,
            command_id=cmd_execution.command_id,
            is_interactive=is_interactive,
            interactive_reasons=interactive_reasons,
        )

        if self.redis_client:
            await self.session_manager._persist_session(session)

        user_id = session.get_user_id()
        if session.has_conversation():
            await self.terminal_logger.log_command(
                session_id=session.conversation_id,
                command=command,
                run_type="autobot",
                status="pending_approval",
                user_id=user_id,
            )

        return session.build_pending_response(
            command=command,
            risk_value=risk.value,
            reasons=reasons,
            description=description,
            command_id=cmd_execution.command_id,
            terminal_session_id=cmd_execution.terminal_session_id,
            is_interactive=is_interactive,
            interactive_reasons=interactive_reasons,
        )

    async def _execute_auto_approved_command(
        self,
        session: AgentTerminalSession,
        command: str,
        risk,
    ) -> Metadata:
        """Execute an auto-approved command (Issue #281: extracted)."""
        task_start_time = time.time()

        if session.has_conversation():
            await self.terminal_logger.log_command(
                session_id=session.conversation_id,
                command=command,
                run_type="autobot",
                status="executing",
                user_id=None,
            )

        result = await self.command_executor.execute_in_pty(session, command)

        task_duration = time.time() - task_start_time
        status = "success" if result.get("status") == "success" else "error"
        self.prometheus_metrics.record_task_execution(
            task_type="command_execution",
            agent_type=session.agent_role.value,
            status=status,
            duration=task_duration,
        )

        if session.has_conversation():
            await self.terminal_logger.log_command(
                session_id=session.conversation_id,
                command=command,
                run_type="autobot",
                status=status,
                result=result,
                user_id=None,
            )

        await self._save_command_to_chat(
            session.conversation_id, command, result, command_type="agent"
        )

        # Interpret result if chat workflow manager available
        await self._interpret_command_result(session, command, result)

        # Update session history and broadcast status (Issue #665: extracted helper)
        await self._finalize_auto_approved_execution(session, command, risk, result)

        return result

    # ============================================================================
    # Helper Methods for auto-approved execution (Issue #665)
    # ============================================================================

    async def _interpret_command_result(
        self,
        session: AgentTerminalSession,
        command: str,
        result: Metadata,
    ) -> None:
        """
        Interpret command result using LLM if available.

        Issue #665: Extracted from _execute_auto_approved_command.

        Args:
            session: Terminal session
            command: Executed command
            result: Execution result
        """
        if session.has_conversation() and self.chat_workflow_manager:
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
                logger.error("[INTERPRETATION] Failed to interpret results: %s", e)

    async def _finalize_auto_approved_execution(
        self,
        session: AgentTerminalSession,
        command: str,
        risk,
        result: Metadata,
    ) -> None:
        """
        Finalize auto-approved execution with history update and broadcast.

        Issue #665: Extracted from _execute_auto_approved_command.

        Args:
            session: Terminal session
            command: Executed command
            risk: Risk level
            result: Execution result (modified in place)
        """
        session.command_history.append({
            "command": command,
            "risk": risk.value,
            "timestamp": time.time(),
            "auto_approved": True,
            "result": result,
        })
        session.last_activity = time.time()

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

    # ============================================================================
    # Helper Methods for _approve_command_internal (Issue #281)
    # ============================================================================

    async def _log_command_approval(
        self,
        session: AgentTerminalSession,
        command: str,
        user_id: Optional[str],
    ) -> None:
        """
        Log command approval to terminal logger.

        Issue #665: Extracted from _execute_approved_command.

        Args:
            session: Terminal session
            command: Command being approved
            user_id: User who approved the command
        """
        if session.has_conversation():
            await self.terminal_logger.log_command(
                session_id=session.conversation_id,
                command=command,
                run_type="manual",
                status="approved",
                user_id=user_id,
            )

    async def _log_command_result(
        self,
        session: AgentTerminalSession,
        command: str,
        result: Metadata,
        user_id: Optional[str],
    ) -> None:
        """
        Log command execution result to terminal logger.

        Issue #665: Extracted from _execute_approved_command.

        Args:
            session: Terminal session
            command: Executed command
            result: Execution result
            user_id: User who approved the command
        """
        if session.has_conversation():
            await self.terminal_logger.log_command(
                session_id=session.conversation_id,
                command=command,
                run_type="manual",
                status="success" if result.get("status") == "success" else "error",
                result=result,
                user_id=user_id,
            )

    async def _post_execution_updates(
        self,
        session: AgentTerminalSession,
        command: str,
        result: Metadata,
        risk_level: str,
        user_id: Optional[str],
        comment: Optional[str],
        auto_approve_future: bool,
    ) -> None:
        """
        Perform all post-execution updates after command runs.

        Issue #665: Extracted from _execute_approved_command.

        Args:
            session: Terminal session
            command: Executed command
            result: Execution result
            risk_level: Risk level of command
            user_id: User who approved
            comment: Approval comment
            auto_approve_future: Whether to auto-approve similar commands
        """
        # Save to chat
        await self._save_command_to_chat(
            session.conversation_id, command, result, command_type="approved"
        )

        # Interpret command with workflow manager
        await self._interpret_approved_command(session, command, result)

        # Update session history
        session.add_approved_to_history(
            command=command,
            risk_level=risk_level,
            user_id=user_id,
            comment=comment,
            result=result,
        )

        # Clear pending and resume
        session.clear_pending_and_resume()

        # Store auto-approve rule if requested
        if auto_approve_future and user_id:
            await self.approval_handler.store_auto_approve_rule(
                user_id=user_id,
                command=command,
                risk_level=risk_level,
            )

        # Update and broadcast status
        await self._update_and_broadcast_approval_status(
            session, command, True, user_id, comment
        )

    async def _execute_approved_command(
        self,
        session: AgentTerminalSession,
        command: str,
        command_id: str,
        risk_level: str,
        user_id: Optional[str],
        comment: Optional[str],
        auto_approve_future: bool,
    ) -> Metadata:
        """
        Execute an approved command and update all tracking.

        Issue #281: Extracted from approve_command.
        Issue #665: Refactored to extract logging and post-execution helpers.

        Args:
            session: Terminal session
            command: Command to execute
            command_id: Unique command ID
            risk_level: Risk level of command
            user_id: User who approved
            comment: Approval comment
            auto_approve_future: Whether to auto-approve similar commands

        Returns:
            Execution result metadata
        """
        # Update queue status
        await self.approval_handler.update_command_queue_status(
            command_id=command_id,
            approved=True,
            user_id=user_id,
            comment=comment,
        )

        try:
            await self._log_command_approval(session, command, user_id)

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

            await self._log_command_result(session, command, result, user_id)
            await self._post_execution_updates(
                session, command, result, risk_level, user_id, comment, auto_approve_future
            )

            return {
                "status": "approved",
                "command": command,
                "result": result,
                "comment": comment,
                "auto_approve_stored": auto_approve_future,
            }

        except Exception as e:
            logger.error("Approved command execution error: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "command": command,
            }

    async def _handle_denied_command(
        self,
        session: AgentTerminalSession,
        command: str,
        command_id: str,
        risk_level: str,
        user_id: Optional[str],
        comment: Optional[str],
    ) -> Metadata:
        """Handle a denied command and update all tracking (Issue #281: extracted)."""
        # Update queue status
        await self.approval_handler.update_command_queue_status(
            command_id=command_id,
            approved=False,
            user_id=user_id,
            comment=comment,
        )

        # Log denial
        if session.has_conversation():
            await self.terminal_logger.log_command(
                session_id=session.conversation_id,
                command=command,
                run_type="manual",
                status="denied",
                user_id=user_id,
            )

        # Update session history
        session.add_denied_to_history(
            command=command,
            risk_level=risk_level,
            user_id=user_id,
            comment=comment,
        )

        # Clear pending and resume
        session.clear_pending_and_resume()

        # Update and broadcast status
        await self._update_and_broadcast_approval_status(
            session, command, False, user_id, comment
        )

        return {
            "status": "denied",
            "command": command,
            "message": "Command execution denied by user",
            "comment": comment,
        }

    async def _interpret_approved_command(
        self, session: AgentTerminalSession, command: str, result: Metadata
    ) -> None:
        """Interpret approved command results with workflow manager (Issue #281: extracted)."""
        if session.has_conversation() and self.chat_workflow_manager:
            try:
                await self.chat_workflow_manager.interpret_terminal_command(
                    command=command,
                    stdout=result.get("stdout", ""),
                    stderr=result.get("stderr", ""),
                    return_code=result.get("return_code", 0),
                    session_id=session.conversation_id,
                )
            except Exception as e:
                logger.error("Failed to interpret approved command results: %s", e)

    async def _update_and_broadcast_approval_status(
        self,
        session: AgentTerminalSession,
        command: str,
        approved: bool,
        user_id: Optional[str],
        comment: Optional[str],
    ) -> None:
        """Update chat and broadcast approval status (Issue #281: extracted)."""
        await self.approval_handler.update_chat_approval_status(
            session=session,
            command=command,
            approved=approved,
            user_id=user_id,
            comment=comment,
        )

        await self.approval_handler.broadcast_approval_status(
            session, command=command, approved=approved, comment=comment
        )

    # ============================================================================
    # Command Execution (delegated to CommandExecutor)
    # ============================================================================

    def _check_agent_permission(
        self,
        session: AgentTerminalSession,
        command: str,
        risk,
    ) -> Optional[Metadata]:
        """
        Check if agent has permission to execute command at given risk level.

        Issue #665: Extracted from execute_command for single responsibility.

        Args:
            session: Terminal session containing agent role
            command: Command being executed
            risk: Assessed risk level of the command

        Returns:
            Error response if permission denied, None if allowed
        """
        allowed, permission_reason = self.approval_handler.check_agent_permission(
            session.agent_role, risk
        )
        if not allowed:
            logger.warning(
                f"Agent {session.agent_id} denied command execution: {permission_reason}"
            )
            return session.get_permission_denied_response(
                permission_reason, command, risk.value
            )
        return None

    async def _check_auto_approval_or_queue(
        self,
        session: AgentTerminalSession,
        command: str,
        description: Optional[str],
        risk,
        reasons: list,
        is_interactive: bool,
        interactive_reasons: list,
    ) -> tuple[bool, Optional[Metadata]]:
        """
        Check auto-approve rules or queue command for manual approval.

        Issue #665: Extracted from execute_command for single responsibility.

        Args:
            session: Terminal session
            command: Command to execute
            description: Optional command description
            risk: Assessed risk level
            reasons: Risk assessment reasons
            is_interactive: Whether command requires stdin
            interactive_reasons: Reasons for interactivity

        Returns:
            Tuple of (is_auto_approved, queue_response_if_not_approved)
        """
        user_id = session.get_user_id()
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
            return True, None

        # Queue for approval
        queue_response = await self._queue_command_for_approval(
            session=session,
            command=command,
            description=description,
            risk=risk,
            reasons=reasons,
            is_interactive=is_interactive,
            interactive_reasons=interactive_reasons,
        )
        return False, queue_response

    async def execute_command(
        self,
        session_id: str,
        command: str,
        description: Optional[str] = None,
        force_approval: bool = False,
    ) -> Metadata:
        """
        Execute a command in an agent terminal session.

        Issue #281: Refactored from 240 lines to use extracted helper methods.
        Issue #665: Further refactored to extract permission and approval logic.

        Args:
            session_id: Agent session ID
            command: Command to execute
            description: Optional command description
            force_approval: Force user approval even for safe commands

        Returns:
            Execution result with security metadata
        """
        # Validate session
        session = await self.get_session(session_id)
        validation_error = self._validate_session_for_execution(session, session_id)
        if validation_error:
            return validation_error

        # Assess command risk and interactivity
        _, risk, reasons, is_interactive, interactive_reasons = self._assess_command(command)

        # Check agent permissions (Issue #665: extracted helper)
        permission_error = self._check_agent_permission(session, command, risk)
        if permission_error:
            return permission_error

        # Check auto-approve or queue for approval (Issue #665: extracted helper)
        is_auto_approved, queue_response = await self._check_auto_approval_or_queue(
            session, command, description, risk, reasons, is_interactive, interactive_reasons
        )
        if not is_auto_approved:
            return queue_response

        # Execute auto-approved command
        try:
            return await self._execute_auto_approved_command(session, command, risk)
        except Exception as e:
            logger.error("Command execution error: %s", e)
            return {"status": "error", "error": str(e), "command": command}

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
                    from utils.encoding_utils import strip_ansi_codes

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
            logger.error("Failed to save %s command to chat: %s", command_type, e)

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
        remember_for_project: bool = False,
        project_path: Optional[str] = None,
    ) -> Metadata:
        """Approve or deny a pending agent command."""
        # Get per-session lock
        approval_lock = await self.approval_handler._get_approval_lock(session_id)
        async with approval_lock:
            return await self._approve_command_internal(
                session_id, approved, user_id, comment, auto_approve_future,
                remember_for_project, project_path
            )

    async def _approve_command_internal(
        self,
        session_id: str,
        approved: bool,
        user_id: Optional[str] = None,
        comment: Optional[str] = None,
        auto_approve_future: bool = False,
        remember_for_project: bool = False,
        project_path: Optional[str] = None,
    ) -> Metadata:
        """
        Internal implementation of approve_command.

        Issue #281: Refactored from 182 lines to use extracted helper methods.
        """
        session = await self.get_session(session_id)
        if not session:
            return {"status": "error", "error": "Session not found"}

        # Issue #372: Use model method
        if not session.has_pending_approval():
            return {"status": "error", "error": "No pending approval"}

        # Issue #372: Use model methods for pending data
        command = session.get_pending_command()
        risk_level = session.get_pending_risk_level()
        command_id = session.get_pending_command_id()

        if approved:
            # Permission v2: Store in project memory if requested
            if remember_for_project and project_path and user_id:
                await CommandApprovalManager.store_approval_memory_v2(
                    command=command,
                    project_path=project_path,
                    user_id=user_id,
                    risk_level=risk_level or "UNKNOWN",
                    tool="Bash",
                    comment=comment,
                )
                logger.info(
                    f"[APPROVAL] Stored in project memory: {project_path}, "
                    f"command={command[:50]}..."
                )

            # Execute approved command (Issue #281: uses helper)
            return await self._execute_approved_command(
                session=session,
                command=command,
                command_id=command_id,
                risk_level=risk_level,
                user_id=user_id,
                comment=comment,
                auto_approve_future=auto_approve_future,
            )
        else:
            # Handle denied command (Issue #281: uses helper)
            return await self._handle_denied_command(
                session=session,
                command=command,
                command_id=command_id,
                risk_level=risk_level,
                user_id=user_id,
                comment=comment,
            )

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
        logger.info("Agent resumed control of session %s", session_id)

        return {
            "status": "success",
            "message": "Agent control resumed",
            "current_state": session.state.value,
        }
