# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tool and command handling for chat workflow.

Handles terminal tool initialization, command execution, tool call parsing,
and approval workflows.
"""

import asyncio
import html
import json
import logging
import re
from typing import Any, Dict, List

from src.async_chat_workflow import WorkflowMessage

logger = logging.getLogger(__name__)


class ToolHandlerMixin:
    """Mixin for tool and command handling."""

    def _init_terminal_tool(self):
        """Initialize terminal tool for command execution."""
        try:
            import backend.api.agent_terminal as agent_terminal_api
            from src.tools.terminal_tool import TerminalTool

            # CRITICAL: Access the global singleton instance directly
            # This ensures sessions created here are visible to the approval API
            if agent_terminal_api._agent_terminal_service_instance is None:
                from backend.services.agent_terminal import AgentTerminalService

                # Pass self to prevent circular initialization loop
                agent_terminal_api._agent_terminal_service_instance = (
                    AgentTerminalService(chat_workflow_manager=self)
                )
                logger.info("Initialized global AgentTerminalService singleton")

            agent_service = agent_terminal_api._agent_terminal_service_instance
            self.terminal_tool = TerminalTool(agent_terminal_service=agent_service)
            logger.info("Terminal tool initialized successfully with singleton service")
        except Exception as e:
            logger.error(f"Failed to initialize terminal tool: {e}")
            self.terminal_tool = None

    def _parse_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response using XML-style markers.

        Supports both uppercase and lowercase tags, and handles HTML entities.

        Args:
            text: LLM response text

        Returns:
            List of tool call dictionaries
        """
        logger.debug(
            f"[_parse_tool_calls] Searching for TOOL_CALL markers in text of length {len(text)}"
        )

        # Decode HTML entities (e.g., &quot; -> ")
        text = html.unescape(text)

        has_tool_call = ('<TOOL_CALL' in text) or ('<tool_call' in text)
        logger.debug(
            f"[_parse_tool_calls] Checking if '<TOOL_CALL' or "
            f"'<tool_call' exists in text: {has_tool_call}"
        )

        tool_calls = []
        # Match both single and double quotes, and both TOOL_CALL and tool_call (case-insensitive)
        # Format: <TOOL_CALL name="..." params='...' OR params="...">...</TOOL_CALL>
        pattern = r'<tool_call\s+name="([^"]+)"\s+params=(["\'])({[^}]+})\2>([^<]*)</tool_call>'

        logger.debug(f"[_parse_tool_calls] Using regex pattern: {pattern}")

        matches = re.finditer(pattern, text, re.IGNORECASE)
        match_count = 0
        for match in matches:
            match_count += 1
            tool_name = match.group(1)
            params_str = match.group(
                3
            )  # Group 2 is the quote character, group 3 is the JSON
            description = match.group(4)

            try:
                params = json.loads(params_str)
                tool_calls.append(
                    {"name": tool_name, "params": params, "description": description}
                )
                logger.debug(
                    f"[_parse_tool_calls] Found TOOL_CALL #{match_count}: "
                    f"name={tool_name}, params={params}"
                )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool call params: {e}")
                logger.error(f"Params string was: {params_str}")
                continue

        logger.info(
            f"[_parse_tool_calls] Total matches found: {match_count}, "
            f"successfully parsed: {len(tool_calls)}"
        )
        return tool_calls

    async def _execute_terminal_command(
        self, session_id: str, command: str, host: str = "main", description: str = ""
    ) -> Dict[str, Any]:
        """
        Execute terminal command via terminal tool.

        Args:
            session_id: Chat session ID
            command: Command to execute
            host: Target host
            description: Command description

        Returns:
            Execution result
        """
        if not self.terminal_tool:
            return {"status": "error", "error": "Terminal tool not available"}

        # Ensure terminal session exists for this conversation
        if not self.terminal_tool.active_sessions.get(session_id):
            # Create session
            session_result = await self.terminal_tool.create_session(
                agent_id=f"chat_agent_{session_id}",
                conversation_id=session_id,
                agent_role="chat_agent",
                host=host,
            )

            if session_result.get("status") != "success":
                return session_result

        # Execute command
        result = await self.terminal_tool.execute_command(
            conversation_id=session_id, command=command, description=description
        )

        return result

    async def _persist_approval_request(
        self, approval_msg: WorkflowMessage, session_id: str, terminal_session_id: str
    ) -> None:
        """Persist approval request to chat history (Issue #332 - extracted helper)."""
        try:
            from src.chat_history import ChatHistoryManager

            chat_mgr = ChatHistoryManager()
            await chat_mgr.add_message(
                sender="assistant",
                text=approval_msg.content,
                message_type="command_approval_request",
                raw_data=approval_msg.metadata,
                session_id=session_id,
            )
            logger.info(
                f"✅ Persisted approval request immediately: session={session_id}, "
                f"terminal={terminal_session_id}"
            )
        except Exception as persist_error:
            logger.error(
                f"Failed to persist approval request immediately: {persist_error}",
                exc_info=True,
            )

    def _check_approval_completion(
        self,
        session_info: Dict[str, Any],
        command: str,
        elapsed_time: float,
        max_wait_time: float,
    ) -> tuple:
        """Check if approval is complete (Issue #332 - extracted helper).

        Returns: (approval_result, status_msg, should_break)
        """
        if not session_info or session_info.get("pending_approval") is not None:
            return None, None, False

        command_history = session_info.get("command_history", [])
        if not command_history:
            logger.warning(
                f"⚠️ [APPROVAL POLLING] pending_approval is None but no command "
                f"history. Breaking after {elapsed_time:.1f}s to prevent infinite loop."
            )
            return None, None, True

        last_command = command_history[-1]
        if last_command.get("command") != command:
            if elapsed_time > max_wait_time - 3590:
                logger.warning(
                    f"⚠️ [APPROVAL POLLING] Timeout: pending_approval is None "
                    f"but command not found in history. Expected: '{command}', "
                    f"Last in history: '{last_command.get('command')}'. "
                    f"Breaking after {elapsed_time:.1f}s."
                )
                return None, None, True
            return None, None, False

        # Found the execution result
        approval_result = last_command.get("result", {})
        logger.info(
            f"✅ [APPROVAL POLLING] Completion detected! Command: {command}, "
            f"Status: {approval_result.get('status')}, Approved by: {last_command.get('approved_by')}"
        )

        approval_status = "approved" if last_command.get("approved_by") else "denied"
        comment = last_command.get("approval_comment") or last_command.get("denial_reason")
        status_msg = {
            "approval_status": approval_status,
            "approval_comment": comment,
        }

        return approval_result, status_msg, True

    async def _handle_pending_approval(
        self,
        session_id: str,
        command: str,
        result: Dict[str, Any],
        terminal_session_id: str,
        description: str,
    ):
        """
        Handle command approval workflow with polling.

        Args:
            session_id: Chat session ID
            command: Command requiring approval
            result: Result from terminal tool (contains approval request info)
            terminal_session_id: Terminal session ID for approval API
            description: Command description

        Yields:
            WorkflowMessage for approval request and status updates
        Returns:
            Approval result dict or None if timeout
        """
        # Build and yield approval request
        approval_msg = WorkflowMessage(
            type="command_approval_request",
            content=result.get("approval_ui_message", "Command requires approval"),
            metadata={
                "command": command,
                "risk_level": result.get("risk"),
                "reasons": result.get("reasons", []),
                "description": description,
                "requires_approval": True,
                "terminal_session_id": terminal_session_id,
                "conversation_id": session_id,
            },
        )
        yield approval_msg

        # Persist approval request (Issue #332 - uses helper)
        await self._persist_approval_request(approval_msg, session_id, terminal_session_id)

        # Yield waiting message
        yield WorkflowMessage(
            type="response",
            content=(
                f"\n\n⏳ Waiting for your approval to execute: `{command}`\n"
                f"Risk level: {result.get('risk')}\n"
                f"Reasons: {', '.join(result.get('reasons', []))}\n"
            ),
            metadata={"message_type": "approval_waiting", "command": command},
        )

        # Poll for approval (Issue #332 - refactored loop)
        logger.info(f"🔍 [APPROVAL POLLING] Waiting for approval of command: {command}")
        logger.info(
            f"🔍 [APPROVAL POLLING] Chat session: {session_id}, Terminal session: {terminal_session_id}"
        )

        max_wait_time = 3600
        poll_interval = 0.5
        elapsed_time = 0
        poll_count = 0
        approval_result = None

        while elapsed_time < max_wait_time:
            await asyncio.sleep(poll_interval)
            elapsed_time += poll_interval
            poll_count += 1

            try:
                session_info = await self.terminal_tool.agent_terminal_service.get_session_info(
                    terminal_session_id
                )

                # Log polling every 10 seconds
                if poll_count % 20 == 0:
                    pending = session_info.get('pending_approval') is not None if session_info else 'NO SESSION'
                    logger.info(
                        f"🔍 [APPROVAL POLLING] Still waiting... (elapsed: {elapsed_time:.1f}s, pending: {pending})"
                    )

                # Check completion (uses helper)
                result_data, status_msg, should_break = self._check_approval_completion(
                    session_info, command, elapsed_time, max_wait_time
                )

                if result_data:
                    approval_result = result_data
                    yield WorkflowMessage(
                        type="metadata_update",
                        content="",
                        metadata={
                            "message_type": "approval_status_update",
                            "terminal_session_id": terminal_session_id,
                            "command": command,
                            **status_msg,
                        },
                    )

                if should_break:
                    break

            except Exception as check_error:
                logger.error(f"Error checking approval status: {check_error}")

        yield approval_result

    async def _process_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        session_id: str,
        terminal_session_id: str,
        ollama_endpoint: str,
        selected_model: str,
    ):
        """
        Process all tool calls from LLM response.

        Args:
            tool_calls: List of parsed tool calls
            session_id: Chat session ID
            terminal_session_id: Terminal session ID
            ollama_endpoint: Ollama API endpoint
            selected_model: LLM model name

        Yields:
            WorkflowMessage for each stage of execution
        Returns:
            Additional text to append to llm_response
        """
        additional_response = ""

        for tool_call in tool_calls:
            if tool_call["name"] == "execute_command":
                command = tool_call["params"].get("command")
                host = tool_call["params"].get("host", "main")
                description = tool_call.get("description", "")

                logger.info(
                    f"[ChatWorkflowManager] Executing command: {command} on {host}"
                )

                # Execute command
                result = await self._execute_terminal_command(
                    session_id=session_id,
                    command=command,
                    host=host,
                    description=description,
                )

                # Handle different result statuses
                if result.get("status") == "pending_approval":
                    # Ensure terminal session ID is available
                    if not terminal_session_id:
                        logger.error(
                            f"No terminal session found for conversation {session_id}"
                        )
                        yield WorkflowMessage(
                            type="error",
                            content="Terminal session error - cannot request approval",
                            metadata={"error": True},
                        )
                        continue

                    # Handle approval workflow - yields messages and returns result
                    approval_result = None
                    async for approval_msg in self._handle_pending_approval(
                        session_id, command, result, terminal_session_id, description
                    ):
                        # Check if this is the final result (not a WorkflowMessage)
                        if isinstance(approval_msg, dict):
                            approval_result = approval_msg
                        else:
                            yield approval_msg

                    # Process approval result
                    if approval_result and approval_result.get("status") == "success":
                        # Yield execution confirmation
                        yield WorkflowMessage(
                            type="response",
                            content=(
                                "\n\n✅ Command approved and executed! Interpreting"
                                "results...\n\n"
                            ),
                            metadata={
                                "message_type": "command_executed",
                                "command": command,
                                "executed": True,
                                "approved": True,
                            },
                        )

                        # Stream interpretation
                        async for interp_chunk in self._interpret_command_results(
                            command,
                            approval_result.get("stdout", ""),
                            approval_result.get("stderr", ""),
                            approval_result.get("return_code", 0),
                            ollama_endpoint,
                            selected_model,
                            streaming=True,
                        ):
                            yield interp_chunk
                            if hasattr(interp_chunk, "content"):
                                additional_response += interp_chunk.content

                    elif approval_result:
                        # Command failed or denied
                        error = approval_result.get(
                            "error", "Command was denied or failed"
                        )
                        additional_response += f"\n\n❌ {error}"
                        yield WorkflowMessage(
                            type="error",
                            content=f"Command execution failed: {error}",
                            metadata={"command": command, "error": True},
                        )
                    else:
                        # Timeout
                        additional_response += (
                            f"\n\n⏱️ Approval timeout for command: {command}"
                        )
                        yield WorkflowMessage(
                            type="error",
                            content=f"Approval timeout for command: {command}",
                            metadata={"command": command, "timeout": True},
                        )

                elif result.get("status") == "success":
                    # Command executed without approval
                    # _interpret_command_results is an async generator, must iterate it
                    interpretation = ""
                    async for msg in self._interpret_command_results(
                        command,
                        result.get("stdout", ""),
                        result.get("stderr", ""),
                        result.get("return_code", 0),
                        ollama_endpoint,
                        selected_model,
                        streaming=False,
                    ):
                        if hasattr(msg, "content"):
                            interpretation += msg.content
                        # Yield the interpretation message to the caller
                        yield msg

                    # Also yield a summary message with all content
                    if interpretation:
                        yield WorkflowMessage(
                            type="response",
                            content=f"\n\n{interpretation}",
                            metadata={
                                "message_type": "command_result_interpretation",
                                "command": command,
                                "executed": True,
                            },
                        )
                    additional_response += f"\n\n{interpretation}"

                elif result.get("status") == "error":
                    # Command failed
                    error = result.get("error", "Unknown error")
                    additional_response += f"\n\n❌ Command execution failed: {error}"
                    yield WorkflowMessage(
                        type="error",
                        content=f"Command failed: {error}",
                        metadata={"command": command, "error": True},
                    )

        # Can't use return in generator - caller will aggregate chunks instead
        # Return value would be: additional_response
