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
            self.active_sessions[conversation_id] = session.session_id

            logger.info(
                f"Created terminal session {session.session_id} "
                f"for conversation {conversation_id}"
            )

            return {
                "status": "success",
                "session_id": session.session_id,
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

        Security workflow:
        1. Find session for conversation
        2. Execute via AgentTerminalService
        3. Risk assessment and approval workflow applied
        4. Return result or pending approval status

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
        if not session_id:
            return {
                "status": "error",
                "error": "No active terminal session for this conversation",
                "hint": "Create session first using create_session()",
            }

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
                f"http://{NetworkConstants.MAIN_HOST}:{NetworkConstants.BACKEND_PORT}"
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
