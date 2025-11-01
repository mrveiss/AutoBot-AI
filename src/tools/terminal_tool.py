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

from src.constants.network_constants import NetworkConstants

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

    async def create_session(
        self,
        agent_id: str,
        conversation_id: str,
        agent_role: str = "chat_agent",
        host: str = "main",
    ) -> Dict[str, Any]:
        """
        Create a new agent terminal session for this conversation.

        Args:
            agent_id: Unique identifier for the agent
            conversation_id: Chat conversation ID
            agent_role: Role of the agent (default: chat_agent)
            host: Target host for commands (default: main)

        Returns:
            Session creation result
        """
        if not self.agent_terminal_service:
            return {
                "status": "error",
                "error": "Agent terminal service not available",
            }

        try:
            # Import here to avoid circular dependency
            from backend.services.agent_terminal_service import AgentRole

            # Parse agent role
            try:
                role_enum = AgentRole[agent_role.upper()]
            except KeyError:
                return {
                    "status": "error",
                    "error": f"Invalid agent role: {agent_role}",
                }

            # Create session
            session = await self.agent_terminal_service.create_session(
                agent_id=agent_id,
                agent_role=role_enum,
                conversation_id=conversation_id,
                host=host,
            )

            # Track session for this conversation
            # CRITICAL: Store AGENT TERMINAL session ID (needed for approval system)
            # Frontend sends approvals to this ID, not PTY session ID
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

        except Exception as e:
            logger.error(f"Error creating terminal session: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }

    async def execute_command(
        self,
        conversation_id: str,
        command: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a command in the agent's terminal session.

        PERMANENT FIX: Auto-recreates inactive sessions to maintain terminal log persistence.

        Core Features:
        1. Terminal log persistence - preserves all commands across restarts
        2. Result interpretation - agent analyzes every command output
        3. Auto-recreation - seamlessly recovers dead sessions

        Security workflow:
        1. Find session for conversation
        2. Check if session is active (PTY alive)
        3. Auto-recreate if inactive (preserves conversation_id)
        4. Execute via AgentTerminalService
        5. Risk assessment and approval workflow applied
        6. Return result or pending approval status

        Args:
            conversation_id: Chat conversation ID
            command: Command to execute
            description: Optional description of command purpose

        Returns:
            Execution result with security metadata
        """
        if not self.agent_terminal_service:
            return {
                "status": "error",
                "error": "Agent terminal service not available",
            }

        # Get session for this conversation
        session_id = self.active_sessions.get(conversation_id)

        # CRITICAL FIX: active_sessions dict is in-memory and wiped on restart
        # Use reusable method to restore session mapping from database
        if not session_id:
            session_id = await self._restore_session_mapping_from_db(conversation_id)

        # CORE LOGIC: Every chat session MUST have an associated terminal session
        # If no session exists at all, auto-create one
        if not session_id:
            logger.info(
                f"No terminal session exists for conversation {conversation_id}. "
                "Auto-creating session (chat sessions MUST have terminal sessions)."
            )

            from backend.services.agent_terminal_service import AgentRole

            # Auto-create terminal session for this chat conversation
            create_result = await self.agent_terminal_service.create_session(
                agent_id=f"chat_agent_{conversation_id}",
                agent_role=AgentRole.CHAT_AGENT,
                conversation_id=conversation_id,
                host="main",
            )

            # Store session mapping - CRITICAL: Use agent terminal session_id, not pty_session_id
            self.active_sessions[conversation_id] = create_result.session_id
            session_id = create_result.session_id

            logger.info(
                f"Terminal session auto-created: conversation={conversation_id}, "
                f"agent_session={session_id}, pty_session={create_result.pty_session_id}"
            )

        # PERMANENT FIX: Check if session is actually active (PTY alive)
        # If session exists but PTY is dead (e.g., after backend restart), auto-recreate it
        else:
            session_info = await self.agent_terminal_service.get_session_info(
                session_id
            )

            if not session_info or not session_info.get("pty_alive", False):
                logger.warning(
                    f"Session {session_id} for conversation {conversation_id} is inactive. "
                    "Auto-recreating to maintain terminal log persistence."
                )

                # Auto-recreate session with same IDs to preserve continuity
                from backend.services.agent_terminal_service import AgentRole

                # Use chat_agent role as default for auto-recreation
                recreate_result = await self.agent_terminal_service.create_session(
                    agent_id=f"chat_agent_{conversation_id}",
                    agent_role=AgentRole.CHAT_AGENT,
                    conversation_id=conversation_id,
                    host="main",
                )

                # Update session mapping - CRITICAL: Use agent terminal session_id, not pty_session_id
                self.active_sessions[conversation_id] = recreate_result.session_id
                session_id = recreate_result.session_id

                logger.info(
                    f"Session auto-recreated: conversation={conversation_id}, "
                    f"agent_session={session_id}, pty_session={recreate_result.pty_session_id}. "
                    "Terminal log continuity maintained."
                )

                # Restore command history to terminal for persistent log
                await self._restore_terminal_history(conversation_id, session_id)

        try:
            # Execute command via service (includes security checks)
            result = await self.agent_terminal_service.execute_command(
                session_id=session_id,
                command=command,
                description=description,
            )

            # Format result for agent
            if result.get("status") == "pending_approval":
                # Command needs user approval
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
                # Command blocked or error
                return {
                    "status": "error",
                    "error": result.get("error"),
                    "command": command,
                }

            else:
                # Command executed successfully
                return {
                    "status": "success",
                    "command": command,
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "return_code": result.get("return_code", 0),
                    "security": result.get("security", {}),
                }

        except Exception as e:
            logger.error(f"Error executing command: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "command": command,
            }

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
            logger.error(f"Error getting session info: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }

    async def get_user_command_history(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get command history from user's interactive terminal session.

        This allows the agent to see what commands the user has run
        in their terminal, enabling context-aware assistance.

        Args:
            conversation_id: Chat conversation ID (used to find user's terminal session)

        Returns:
            Command history with timestamps and risk levels
        """
        try:
            # Import httpx for API call
            import httpx

            from src.constants.network_constants import NetworkConstants

            # Get user's terminal session ID from conversation
            # For now, we'll need to list all sessions and find the user's
            # In production, this mapping should be stored

            backend_url = (
                f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
            )

            async with httpx.AsyncClient(timeout=5.0) as client:
                # List all terminal sessions
                response = await client.get(f"{backend_url}/api/terminal/sessions")

                if response.status_code != 200:
                    return {
                        "status": "error",
                        "error": "Failed to list terminal sessions",
                    }

                sessions_data = response.json()
                sessions = sessions_data.get("sessions", [])

                # Find user's active terminal session
                # User sessions have user_id "default" and are not agent sessions
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

                # Get history from first active user session
                user_session_id = user_sessions[0]["session_id"]

                history_response = await client.get(
                    f"{backend_url}/api/terminal/sessions/{user_session_id}/history"
                )

                if history_response.status_code != 200:
                    return {
                        "status": "error",
                        "error": "Failed to retrieve command history",
                    }

                history_data = history_response.json()

                return {
                    "status": "success",
                    "session_id": user_session_id,
                    "history": history_data.get("history", []),
                    "total_commands": history_data.get("total_commands", 0),
                }

        except Exception as e:
            logger.error(f"Error getting user command history: {e}", exc_info=True)
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
            logger.error(f"Error closing session: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }

    async def _restore_session_mapping_from_db(
        self, conversation_id: str
    ) -> Optional[str]:
        """
        REUSABLE: Restore session ID from database when active_sessions dict is empty.

        The active_sessions dictionary is in-memory and gets wiped on backend restart.
        This method queries the terminal API to restore the mapping from persistent storage.

        Pattern: Database Fallback for In-Memory State Recovery
        - Checks persistent storage when in-memory state is lost
        - Restores mapping to avoid "session not found" errors
        - Can be called from any method that needs session IDs

        Args:
            conversation_id: Chat conversation ID to look up

        Returns:
            Session ID if found in database, None otherwise

        Example:
            >>> session_id = await self._restore_session_mapping_from_db(conv_id)
            >>> if session_id:
            >>>     # Session restored from database
            >>>     self.active_sessions[conv_id] = session_id
        """
        try:
            import httpx
            from src.constants.network_constants import NetworkConstants

            # Query AGENT terminal API for sessions linked to this conversation
            # CRITICAL: Use /api/agent-terminal/sessions (not /api/terminal/sessions)
            backend_url = (
                f"http://{NetworkConstants.MAIN_MACHINE_IP}:"
                f"{NetworkConstants.BACKEND_PORT}"
            )

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{backend_url}/api/agent-terminal/sessions",
                    params={"conversation_id": conversation_id},
                )

                if response.status_code == 200:
                    data = response.json()
                    sessions = data.get("sessions", [])

                    if sessions and len(sessions) > 0:
                        # Found existing session - restore to active_sessions mapping
                        db_session = sessions[0]
                        session_id = db_session.get("session_id")
                        if session_id:
                            self.active_sessions[conversation_id] = session_id
                            logger.info(
                                f"Restored session mapping from database: "
                                f"conversation={conversation_id}, session={session_id}"
                            )
                            return session_id

        except Exception as e:
            logger.debug(f"Failed to query database for session: {e}")

        return None

    async def _restore_terminal_history(
        self, conversation_id: str, session_id: str
    ) -> None:
        """
        Restore command history to terminal for persistent log.

        PERMANENT FIX: Maintains terminal log across restarts by replaying
        command history from chat messages into the PTY terminal.

        Args:
            conversation_id: Chat conversation ID
            session_id: PTY session ID to restore history to
        """
        try:
            import httpx
            from src.constants.network_constants import NetworkConstants

            backend_url = (
                f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
            )

            async with httpx.AsyncClient(timeout=10.0) as client:
                # Fetch chat messages for this conversation
                response = await client.get(
                    f"{backend_url}/api/chats/{conversation_id}/messages"
                )

                if response.status_code != 200:
                    logger.warning(
                        f"Failed to fetch chat history for restoration: {response.status_code}"
                    )
                    return

                messages = response.json().get("messages", [])

                # Filter for command-related messages
                command_messages = [
                    msg
                    for msg in messages
                    if msg.get("metadata", {}).get("type") == "command"
                    or "command" in msg.get("content", "").lower()[:50]
                ]

                if not command_messages:
                    logger.info(f"No command history to restore for {conversation_id}")
                    return

                # Write restoration header to terminal
                session = self.agent_terminal_service.sessions.get(session_id)
                if session and session.pty_session_id:
                    header = (
                        "\033[1;36m"  # Cyan bold
                        "═══════════════════════════════════════════════════════════════\n"
                        "  SESSION RESTORED - Command History Replay\n"
                        f"  Conversation: {conversation_id[:16]}...\n"
                        f"  Commands: {len(command_messages)} entries\n"
                        "═══════════════════════════════════════════════════════════════\n"
                        "\033[0m"  # Reset
                    )
                    self.agent_terminal_service._write_to_pty(session, header)

                    # Replay commands and outputs
                    for msg in command_messages[-20:]:  # Last 20 commands
                        content = msg.get("content", "")
                        timestamp = msg.get("timestamp", "")

                        # Format and write to terminal
                        history_entry = (
                            f"\033[90m[{timestamp}]\033[0m "  # Gray timestamp
                            f"{content}\n"
                        )
                        self.agent_terminal_service._write_to_pty(
                            session, history_entry
                        )

                    footer = (
                        "\033[1;36m"
                        "═══════════════════════════════════════════════════════════════\n"
                        "  History restoration complete. Terminal ready.\n"
                        "═══════════════════════════════════════════════════════════════\n"
                        "\033[0m"
                    )
                    self.agent_terminal_service._write_to_pty(session, footer)

                logger.info(
                    f"Restored {len(command_messages)} command entries to terminal {session_id}"
                )

        except Exception as e:
            logger.error(f"Error restoring terminal history: {e}", exc_info=True)
            # Don't fail command execution if history restoration fails

    def get_tool_description(self) -> Dict[str, Any]:
        """
        Get tool description for agent use.

        Returns:
            Tool description with methods and usage
        """
        return {
            "name": "terminal_tool",
            "description": "Secure terminal access for command execution with approval workflow",
            "methods": {
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
                    "parameters": {
                        "conversation_id": "Chat conversation ID",
                    },
                    "returns": "Session information",
                },
                "close_session": {
                    "description": "Close the terminal session",
                    "parameters": {
                        "conversation_id": "Chat conversation ID",
                    },
                    "returns": "Close result",
                },
            },
            "security_features": {
                "risk_assessment": "All commands assessed for security risk",
                "approval_workflow": "MODERATE+ risk commands require user approval",
                "user_control": "Users can interrupt and take control at any time",
                "audit_logging": "All commands logged with security metadata",
            },
            "usage_example": {
                "step1": "create_session(agent_id='chat_agent_1', conversation_id='abc123')",
                "step2": "execute_command(conversation_id='abc123', command='ls -la')",
                "step3": "close_session(conversation_id='abc123')",
            },
        }


# Global instance (will be initialized with service)
_terminal_tool_instance: Optional[TerminalTool] = None


def get_terminal_tool(agent_terminal_service=None) -> TerminalTool:
    """
    Get the global TerminalTool instance.

    Args:
        agent_terminal_service: Service to use (initializes on first call)

    Returns:
        TerminalTool instance
    """
    global _terminal_tool_instance

    if _terminal_tool_instance is None:
        _terminal_tool_instance = TerminalTool(agent_terminal_service)
    elif agent_terminal_service is not None:
        # Update service if provided
        _terminal_tool_instance.agent_terminal_service = agent_terminal_service

    return _terminal_tool_instance
