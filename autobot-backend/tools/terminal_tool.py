# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Terminal Tool for Chat Workflow Integration

Provides programmatic terminal access for AI agents during chat conversations.

Security Integration:
- All commands go through AgentTerminalService
- Risk assessment via SecureCommandExecutor
- Approval workflow for MODERATE+ risk commands
- Comprehensive audit logging
- User interrupt capability
"""

import threading
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from services.agent_terminal.errors import (
    POST_EXECUTION_FAILED_CODE,
    POST_EXECUTION_FAILED_STATUS,
    SESSION_SETUP_FAILED_CODE,
    PostExecutionError,
    execution_failed_response,
    post_execution_failed_response,
    post_execution_guard,
)
from tools import terminal_backend_client, terminal_tool_schema

logger = get_logger(__name__)


class TerminalTool:
    """
    Terminal access tool for chat agents.

    Provides secure command execution with approval workflow and user control.
    """

    def __init__(self, agent_terminal_service=None):
        """
        Initialize terminal tool.

        Args:
            agent_terminal_service: AgentTerminalService instance
        """
        self.agent_terminal_service = agent_terminal_service
        self.active_sessions: Dict[str, str] = {}  # conversation_id -> session_id

    # Issue #321: Delegation methods to reduce message chains (Law of Demeter)
    def get_session(self, session_id: str) -> Any | None:
        """Get session from agent terminal service sessions dict."""
        if self.agent_terminal_service:
            return self.agent_terminal_service.sessions.get(session_id)
        return None

    def _parse_agent_role(self, agent_role: str):
        """Parse agent role string to enum. Returns (role_enum, error_dict or None)."""
        from services.command_approval_manager import AgentRole

        try:
            return AgentRole[agent_role.upper()], None
        except KeyError:
            return None, {
                "status": "error",
                "error": f"Invalid agent role: {agent_role}",
            }

    def _format_session_result(self, session, conversation_id: str) -> Dict[str, Any]:
        """Format session creation result for response."""
        # CRITICAL: Store AGENT TERMINAL session ID (needed for approval system)
        self.active_sessions[conversation_id] = session.session_id

        logger.info(
            f"Created terminal session {session.pty_session_id} "
            f"for conversation {conversation_id} "
            f"(agent terminal session: {session.session_id})"
        )

        return {
            "status": "success",
            "session_id": session.pty_session_id,  # Return PTY session ID (matches chat)
            "agent_role": session.agent_role.value,
            "host": session.host,
        }

    async def create_session(
        self,
        agent_id: str,
        conversation_id: str,
        agent_role: str = "chat_agent",
        host: str = "main",
    ) -> Dict[str, Any]:
        """Create a new agent terminal session for this conversation (Issue #281 refactor)."""
        if not self.agent_terminal_service:
            return {"status": "error", "error": "Agent terminal service not available"}

        try:
            role_enum, error = self._parse_agent_role(agent_role)
            if error:
                return error

            session = await self.agent_terminal_service.create_session(
                agent_id=agent_id,
                agent_role=role_enum,
                conversation_id=conversation_id,
                host=host,
            )
            return self._format_session_result(session, conversation_id)

        except Exception as e:
            logger.error("Error creating terminal session: %s", e, exc_info=True)
            return {"status": "error", "error": "Terminal session creation failed"}

    async def _create_new_session(self, conversation_id: str) -> str:
        """Create a new terminal session for a conversation. Returns session_id."""
        from services.command_approval_manager import AgentRole

        create_result = await self.agent_terminal_service.create_session(
            agent_id=f"chat_agent_{conversation_id}",
            agent_role=AgentRole.CHAT_AGENT,
            conversation_id=conversation_id,
            host="main",
        )
        self.active_sessions[conversation_id] = create_result.session_id
        logger.info(
            f"Terminal session auto-created: conversation={conversation_id}, "
            f"agent_session={create_result.session_id}, pty_session={create_result.pty_session_id}"
        )
        return create_result.session_id

    async def _recreate_inactive_session(self, conversation_id: str, old_session_id: str) -> str:
        """Recreate an inactive session. Returns new session_id."""
        from services.command_approval_manager import AgentRole

        logger.warning(
            f"Session {old_session_id} for conversation {conversation_id} is inactive. "
            "Auto-recreating to maintain terminal log persistence."
        )
        recreate_result = await self.agent_terminal_service.create_session(
            agent_id=f"chat_agent_{conversation_id}",
            agent_role=AgentRole.CHAT_AGENT,
            conversation_id=conversation_id,
            host="main",
        )
        self.active_sessions[conversation_id] = recreate_result.session_id
        logger.info(
            f"Session auto-recreated: conversation={conversation_id}, "
            f"agent_session={recreate_result.session_id}, pty_session={recreate_result.pty_session_id}"
        )
        await self._restore_terminal_history(conversation_id, recreate_result.session_id)
        return recreate_result.session_id

    async def _ensure_active_session(self, conversation_id: str) -> str:
        """Ensure an active session exists for conversation. Returns session_id."""
        session_id = self.active_sessions.get(conversation_id)

        if not session_id:
            session_id = await self._restore_session_mapping_from_db(conversation_id)

        if not session_id:
            logger.info("No terminal session for %s. Auto-creating.", conversation_id)
            return await self._create_new_session(conversation_id)

        session_info = await self.agent_terminal_service.get_session_info(session_id)
        if not session_info or not session_info.get("pty_alive", False):
            return await self._recreate_inactive_session(conversation_id, session_id)

        return session_id

    def _format_execution_result(self, result: Dict[str, Any], command: str, description: str | None) -> Dict[str, Any]:
        """Format command execution result for agent response.

        A dispatcher over the four outcomes the service can report. Each branch
        is its own helper so that adding an outcome cannot be done by widening
        an existing one -- which is how ``completed_with_errors`` came to be
        reported as a clean success (#15110).
        """
        status = result.get("status")
        if status == "pending_approval":
            return self._format_pending_approval(result, command, description)
        elif status == "error":
            return self._format_command_failure(result, command)
        elif status == POST_EXECUTION_FAILED_STATUS:
            return self._format_post_execution_failure(result, command)
        return {
            "status": "success",
            "command": command,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "return_code": result.get("return_code", 0),
            "security": result.get("security", {}),
        }

    @staticmethod
    def _format_pending_approval(result: Dict[str, Any], command: str, description: str | None) -> Dict[str, Any]:
        """The command has not run: a human has to allow it first."""
        return {
            "status": "pending_approval",
            "message": "Command requires user approval before execution",
            "command": command,
            "risk": result.get("risk"),
            "reasons": result.get("reasons"),
            "description": description,
            "approval_ui_message": (
                f"Agent wants to execute: `{command}`\n"
                f"Risk level: {result.get('risk')}\n"
                f"Reasons: {', '.join(result.get('reasons', []))}\n"
                f"Approve execution?"
            ),
        }

    @staticmethod
    def _format_command_failure(result: Dict[str, Any], command: str) -> Dict[str, Any]:
        """The command ran and failed. What it printed is the failure report.

        #14148: never emit a ``None`` under a key callers read with a
        ``.get(key, default)`` -- the default will not apply and the ``None``
        travels onward. Fall back through the fields the PTY result actually
        carries before giving up.

        #14141: carry stdout/stderr/return_code through, mirroring the success
        branch. This used to return only status, error and command, so every
        field describing WHAT the command did was discarded -- and
        ``_build_pty_result`` sets ``stderr: ""`` (the PTY combines the streams)
        and no ``error`` key at all, so the message always degraded to the
        literal fallback and the failure report itself never reached the model.
        A test runner writing "47 failed, 200 passed" to stdout and exiting 1
        arrived at the continuation prompt as a generic placeholder.
        """
        return {
            "status": "error",
            "error": result.get("error") or result.get("stderr") or "Command failed with no error detail",
            "command": command,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "return_code": result.get("return_code", 1),
        }

    @staticmethod
    def _format_post_execution_failure(result: Dict[str, Any], command: str) -> Dict[str, Any]:
        """A command that ran, and a step after it that did not (#15110).

        This status had no branch and fell through to the success branch above.
        That was right about the output -- stdout, stderr and return code were
        carried -- and silent about the failure, so the model was told the run
        was clean while ``post_execution_error`` was dropped.

        Per #14148 no key here may carry a ``None``: every fallback resolves to
        a value a caller's ``.get(key, default)`` would otherwise not replace.
        """
        detail = result.get("post_execution_error") or result.get("error") or "post-execution step failed"
        return {
            "status": POST_EXECUTION_FAILED_STATUS,
            "error_code": POST_EXECUTION_FAILED_CODE,
            "command": command,
            "command_status": result.get("command_status") or "success",
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "return_code": result.get("return_code", 0),
            "security": result.get("security", {}),
            "post_execution_error": detail,
            "error": f"Command ran; a post-execution step failed: {detail}",
        }

    async def execute_command(
        self, conversation_id: str, command: str, description: str | None = None
    ) -> Dict[str, Any]:
        """Execute a command in the agent's terminal session with auto-session recovery.

        #15110: one ``except Exception`` used to wrap session recovery, the
        service call *and* the formatting after it, so "no terminal session
        could be created", "the command failed" and "the formatter raised" all
        reached the model as the same four words. Each stage now closes on its
        own outcome, and the `TypeError` / `AttributeError` the service
        deliberately re-raises (#15073) travels on rather than being relabelled
        a failed command.
        """
        if not self.agent_terminal_service:
            return {"status": "error", "error": "Agent terminal service not available"}

        try:
            session_id = await self._ensure_active_session(conversation_id)
        except Exception as exc:
            logger.error("No terminal session for conversation %s", conversation_id, exc_info=True)
            return self._session_setup_failed(command, exc)

        return await self._run_and_format(session_id, command, description)

    @staticmethod
    def _session_setup_failed(command: str, exc: BaseException) -> Dict[str, Any]:
        """The command never ran: there was nowhere to run it.

        Named separately from an execution failure because the two send whoever
        reads them to different places -- the session store and the PTY, versus
        the command itself.
        """
        return {
            "status": "error",
            "error": f"No terminal session could be established: {type(exc).__name__}: {exc}",
            "error_code": SESSION_SETUP_FAILED_CODE,
            "command": command,
        }

    async def _run_and_format(self, session_id: str, command: str, description: str | None) -> Dict[str, Any]:
        """Execute, then format, distinguishing a failed command from failed bookkeeping.

        ``post_execution_guard`` opens only once the service has returned, so
        anything it catches is by construction a defect in what happens after
        the command ran -- the same split ``services/agent_terminal/service.py``
        makes one layer down, through the same helper rather than a third copy
        of it.
        """
        try:
            result = await self.agent_terminal_service.execute_command(
                session_id=session_id, command=command, description=description
            )
            with post_execution_guard(result):
                return self._format_execution_result(result, command, description)
        except PostExecutionError as exc:
            logger.error("Command ran; formatting its result failed: %s", exc, exc_info=True)
            return post_execution_failed_response(command, exc)
        except (TypeError, AttributeError):
            raise
        except Exception:
            logger.error("Terminal command execution error", exc_info=True)
            return execution_failed_response(command)

    async def get_session_info(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get information about the terminal session for this conversation.

        Args:
            conversation_id: Chat conversation ID

        Returns:
            Session information
        """
        if not self.agent_terminal_service:
            return {
                "status": "error",
                "error": "Agent terminal service not available",
            }

        session_id = self.active_sessions.get(conversation_id)
        if not session_id:
            return {
                "status": "error",
                "error": "No active terminal session",
            }

        try:
            session_info = await self.agent_terminal_service.get_session_info(session_id)

            if not session_info:
                return {
                    "status": "error",
                    "error": "Session not found",
                }

            return {
                "status": "success",
                **session_info,
            }

        except Exception as e:
            logger.error("Error getting session info: %s", e, exc_info=True)
            return {
                "status": "error",
                "error": "Failed to retrieve session info",
            }

    async def get_user_command_history(self, conversation_id: str) -> Dict[str, Any]:
        """Get command history from user's interactive terminal session (Issue #281 refactor)."""
        try:
            sessions, error = await terminal_backend_client.list_terminal_sessions()
            if error:
                return error

            # Find user's active terminal session (user_id "default", not agent sessions)
            user_sessions = [s for s in sessions if s.get("is_active") and s.get("user_id") == "default"]

            if not user_sessions:
                return {
                    "status": "success",
                    "history": [],
                    "message": "No active user terminal session found",
                }

            user_session_id = user_sessions[0]["session_id"]
            history_data, error = await terminal_backend_client.fetch_session_history(user_session_id)
            if error:
                return error

            return {
                "status": "success",
                "session_id": user_session_id,
                "history": history_data.get("history", []),
                "total_commands": history_data.get("total_commands", 0),
            }

        except Exception as e:
            logger.error("Error getting user command history: %s", e, exc_info=True)
            return {"status": "error", "error": "Failed to retrieve command history"}

    async def close_session(self, conversation_id: str) -> Dict[str, Any]:
        """
        Close the terminal session for this conversation.

        Args:
            conversation_id: Chat conversation ID

        Returns:
            Close result
        """
        if not self.agent_terminal_service:
            return {
                "status": "error",
                "error": "Agent terminal service not available",
            }

        session_id = self.active_sessions.get(conversation_id)
        if not session_id:
            return {
                "status": "error",
                "error": "No active terminal session",
            }

        try:
            success = await self.agent_terminal_service.close_session(session_id)

            if success:
                # Remove from active sessions
                del self.active_sessions[conversation_id]

                logger.info(f"Closed terminal session for conversation {conversation_id}")

                return {
                    "status": "success",
                    "message": "Terminal session closed",
                }
            else:
                return {
                    "status": "error",
                    "error": "Failed to close session",
                }

        except Exception as e:
            logger.error("Error closing session: %s", e, exc_info=True)
            return {
                "status": "error",
                "error": "Failed to close session",
            }

    async def _restore_session_mapping_from_db(self, conversation_id: str) -> str | None:
        """Restore session ID from database when active_sessions dict is empty (Issue #281 refactor)."""
        try:
            sessions = await terminal_backend_client.query_agent_terminal_sessions(conversation_id)

            if sessions:
                session_id = sessions[0].get("session_id")
                if session_id:
                    self.active_sessions[conversation_id] = session_id
                    logger.info(
                        "Restored session mapping from database: conversation=%s, session=%s",
                        conversation_id,
                        session_id,
                    )
                    return session_id

        except Exception as e:
            logger.debug("Failed to query database for session: %s", e)

        return None

    def _build_restoration_header(self, conversation_id: str, command_count: int) -> str:
        """Build the restoration header string for terminal display."""
        return (
            "\033[1;36m"  # Cyan bold
            "═══════════════════════════════════════════════════════════════\n"
            "  SESSION RESTORED - Command History Replay\n"
            f"  Conversation: {conversation_id[:16]}...\n"
            f"  Commands: {command_count} entries\n"
            "═══════════════════════════════════════════════════════════════\n"
            "\033[0m"  # Reset
        )

    def _build_restoration_footer(self) -> str:
        """Build the restoration footer string for terminal display."""
        return (
            "\033[1;36m"
            "═══════════════════════════════════════════════════════════════\n"
            "  History restoration complete. Terminal ready.\n"
            "═══════════════════════════════════════════════════════════════\n"
            "\033[0m"
        )

    def _write_history_to_pty(self, session, command_messages: list) -> None:
        """Write command history entries to PTY terminal."""
        for msg in command_messages[-20:]:  # Last 20 commands
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")
            history_entry = f"\033[90m[{timestamp}]\033[0m {content}\n"
            self.agent_terminal_service._write_to_pty(session, history_entry)

    async def _restore_terminal_history(self, conversation_id: str, session_id: str) -> None:
        """Restore command history to terminal for persistent log (Issue #281 refactor)."""
        try:
            command_messages = await terminal_backend_client.fetch_command_messages(conversation_id)

            if not command_messages:
                logger.info("No command history to restore for %s", conversation_id)
                return

            # Issue #321: Use delegation method to reduce message chains
            session = self.get_session(session_id)
            if session and session.pty_session_id:
                header = self._build_restoration_header(conversation_id, len(command_messages))
                self.agent_terminal_service._write_to_pty(session, header)
                self._write_history_to_pty(session, command_messages)
                self.agent_terminal_service._write_to_pty(session, self._build_restoration_footer())

            logger.info(
                "Restored %s command entries to terminal %s",
                len(command_messages),
                session_id,
            )

        except Exception as e:
            logger.error("Error restoring terminal history: %s", e, exc_info=True)

    def get_tool_description(self) -> Dict[str, Any]:
        """Get tool description for agent use (Issue #281 refactor)."""
        return terminal_tool_schema.tool_description()


# Global instance (will be initialized with service)
_terminal_tool_instance: TerminalTool | None = None
_terminal_tool_lock = threading.Lock()


def get_terminal_tool(agent_terminal_service=None) -> TerminalTool:
    """
    Get the global TerminalTool instance (thread-safe).

    Args:
        agent_terminal_service: Service to use (initializes on first call)

    Returns:
        TerminalTool instance
    """
    global _terminal_tool_instance

    if _terminal_tool_instance is None:
        with _terminal_tool_lock:
            # Double-check after acquiring lock
            if _terminal_tool_instance is None:
                _terminal_tool_instance = TerminalTool(agent_terminal_service)
    elif agent_terminal_service is not None:
        # Update service if provided (lock not needed for simple assignment)
        _terminal_tool_instance.agent_terminal_service = agent_terminal_service

    return _terminal_tool_instance
