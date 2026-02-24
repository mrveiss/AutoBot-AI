# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

import logging
from typing import Any, Dict, Optional

from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)


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
    def get_session(self, session_id: str) -> Optional[Any]:
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
            return {"status": "error", "error": str(e)}

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

    async def _recreate_inactive_session(
        self, conversation_id: str, old_session_id: str
    ) -> str:
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
        await self._restore_terminal_history(
            conversation_id, recreate_result.session_id
        )
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

    def _format_execution_result(
        self, result: Dict[str, Any], command: str, description: Optional[str]
    ) -> Dict[str, Any]:
        """Format command execution result for agent response."""
        if result.get("status") == "pending_approval":
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
        elif result.get("status") == "error":
            return {"status": "error", "error": result.get("error"), "command": command}
        else:
            return {
                "status": "success",
                "command": command,
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "return_code": result.get("return_code", 0),
                "security": result.get("security", {}),
            }

    async def execute_command(
        self, conversation_id: str, command: str, description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a command in the agent's terminal session with auto-session recovery."""
        if not self.agent_terminal_service:
            return {"status": "error", "error": "Agent terminal service not available"}

        try:
            session_id = await self._ensure_active_session(conversation_id)
            result = await self.agent_terminal_service.execute_command(
                session_id=session_id, command=command, description=description
            )
            return self._format_execution_result(result, command, description)
        except Exception as e:
            logger.error("Error executing command: %s", e, exc_info=True)
            return {"status": "error", "error": str(e), "command": command}

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
            session_info = await self.agent_terminal_service.get_session_info(
                session_id
            )

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
                "error": str(e),
            }

    async def _list_terminal_sessions(self, backend_url: str) -> tuple:
        """List terminal sessions from backend. Returns (sessions_list, error_dict or None)."""
        import aiohttp

        http_client = get_http_client()
        async with await http_client.get(
            f"{backend_url}/api/terminal/sessions",
            timeout=aiohttp.ClientTimeout(total=5.0),
        ) as response:
            if response.status != 200:
                return [], {
                    "status": "error",
                    "error": "Failed to list terminal sessions",
                }
            sessions_data = await response.json()
            return sessions_data.get("sessions", []), None

    async def _fetch_session_history(self, backend_url: str, session_id: str) -> tuple:
        """Fetch command history for a session. Returns (history_data, error_dict or None)."""
        import aiohttp

        http_client = get_http_client()
        async with await http_client.get(
            f"{backend_url}/api/terminal/sessions/{session_id}/history",
            timeout=aiohttp.ClientTimeout(total=5.0),
        ) as response:
            if response.status != 200:
                return None, {
                    "status": "error",
                    "error": "Failed to retrieve command history",
                }
            return await response.json(), None

    async def get_user_command_history(self, conversation_id: str) -> Dict[str, Any]:
        """Get command history from user's interactive terminal session (Issue #281 refactor)."""
        try:
            from constants.network_constants import NetworkConstants

            backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"

            sessions, error = await self._list_terminal_sessions(backend_url)
            if error:
                return error

            # Find user's active terminal session (user_id "default", not agent sessions)
            user_sessions = [
                s
                for s in sessions
                if s.get("is_active") and s.get("user_id") == "default"
            ]

            if not user_sessions:
                return {
                    "status": "success",
                    "history": [],
                    "message": "No active user terminal session found",
                }

            user_session_id = user_sessions[0]["session_id"]
            history_data, error = await self._fetch_session_history(
                backend_url, user_session_id
            )
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
            return {"status": "error", "error": str(e)}

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

                logger.info(
                    f"Closed terminal session for conversation {conversation_id}"
                )

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
                "error": str(e),
            }

    async def _query_agent_terminal_sessions(self, conversation_id: str) -> list:
        """Query agent terminal API for sessions linked to conversation. Returns empty list on error."""
        import aiohttp
        from constants.network_constants import NetworkConstants

        # CRITICAL: Use /api/agent-terminal/sessions (not /api/terminal/sessions)
        backend_url = (
            f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
        )

        http_client = get_http_client()
        async with await http_client.get(
            f"{backend_url}/api/agent-terminal/sessions",
            params={"conversation_id": conversation_id},
            timeout=aiohttp.ClientTimeout(total=5.0),
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("sessions", [])
        return []

    async def _restore_session_mapping_from_db(
        self, conversation_id: str
    ) -> Optional[str]:
        """Restore session ID from database when active_sessions dict is empty (Issue #281 refactor)."""
        try:
            sessions = await self._query_agent_terminal_sessions(conversation_id)

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

    async def _fetch_command_messages(self, conversation_id: str) -> list:
        """Fetch command-related messages from chat history. Returns empty list on error."""
        import aiohttp
        from constants.network_constants import NetworkConstants

        backend_url = (
            f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
        )

        http_client = get_http_client()
        async with await http_client.get(
            f"{backend_url}/api/chats/{conversation_id}/messages",
            timeout=aiohttp.ClientTimeout(total=10.0),
        ) as response:
            if response.status != 200:
                logger.warning(
                    "Failed to fetch chat history for restoration: %s", response.status
                )
                return []

            data = await response.json()
            messages = data.get("messages", [])

        # Filter for command-related messages
        return [
            msg
            for msg in messages
            if msg.get("metadata", {}).get("type") == "command"
            or "command" in msg.get("content", "").lower()[:50]
        ]

    def _build_restoration_header(
        self, conversation_id: str, command_count: int
    ) -> str:
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

    async def _restore_terminal_history(
        self, conversation_id: str, session_id: str
    ) -> None:
        """Restore command history to terminal for persistent log (Issue #281 refactor)."""
        try:
            command_messages = await self._fetch_command_messages(conversation_id)

            if not command_messages:
                logger.info("No command history to restore for %s", conversation_id)
                return

            # Issue #321: Use delegation method to reduce message chains
            session = self.get_session(session_id)
            if session and session.pty_session_id:
                header = self._build_restoration_header(
                    conversation_id, len(command_messages)
                )
                self.agent_terminal_service._write_to_pty(session, header)
                self._write_history_to_pty(session, command_messages)
                self.agent_terminal_service._write_to_pty(
                    session, self._build_restoration_footer()
                )

            logger.info(
                "Restored %s command entries to terminal %s",
                len(command_messages),
                session_id,
            )

        except Exception as e:
            logger.error("Error restoring terminal history: %s", e, exc_info=True)

    def _get_method_descriptions(self) -> Dict[str, Any]:
        """Get method descriptions for tool documentation."""
        return {
            "create_session": {
                "description": "Create a new terminal session for this conversation",
                "parameters": {
                    "agent_id": "Unique identifier for the agent",
                    "conversation_id": "Chat conversation ID",
                    "agent_role": "Role (chat_agent, automation_agent, system_agent, admin_agent)",
                    "host": "Target host (main, frontend, npu-worker, redis, ai-stack, browser)",
                },
                "returns": "Session creation result",
            },
            "execute_command": {
                "description": "Execute a command in the terminal session",
                "parameters": {
                    "conversation_id": "Chat conversation ID",
                    "command": "Command to execute",
                    "description": "Optional description of command purpose",
                },
                "returns": "Execution result or pending approval status",
            },
            "get_session_info": {
                "description": "Get information about the terminal session",
                "parameters": {"conversation_id": "Chat conversation ID"},
                "returns": "Session information",
            },
            "close_session": {
                "description": "Close the terminal session",
                "parameters": {"conversation_id": "Chat conversation ID"},
                "returns": "Close result",
            },
        }

    def _get_security_features(self) -> Dict[str, str]:
        """Get security features documentation."""
        return {
            "risk_assessment": "All commands assessed for security risk",
            "approval_workflow": "MODERATE+ risk commands require user approval",
            "user_control": "Users can interrupt and take control at any time",
            "audit_logging": "All commands logged with security metadata",
        }

    def get_tool_description(self) -> Dict[str, Any]:
        """Get tool description for agent use (Issue #281 refactor)."""
        return {
            "name": "terminal_tool",
            "description": "Secure terminal access for command execution with approval workflow",
            "methods": self._get_method_descriptions(),
            "security_features": self._get_security_features(),
            "usage_example": {
                "step1": "create_session(agent_id='chat_agent_1', conversation_id='abc123')",
                "step2": "execute_command(conversation_id='abc123', command='ls -la')",
                "step3": "close_session(conversation_id='abc123')",
            },
        }


# Global instance (will be initialized with service)
import threading as _threading_terminal

_terminal_tool_instance: Optional[TerminalTool] = None
_terminal_tool_lock = _threading_terminal.Lock()


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
