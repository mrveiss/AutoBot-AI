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
from src.utils.errors import RepairableException

logger = logging.getLogger(__name__)

# Issue #650: Pre-compiled regex for tool call parsing (performance optimization)
# Handles both uppercase and lowercase TOOL_CALL tags with nested JSON in params
_TOOL_CALL_PATTERN = re.compile(
    r'<tool_call\s+name="([^"]+)"\s+params=(["\'])(.+?)\2>([^<]*)</tool_call>',
    re.IGNORECASE | re.DOTALL,
)

# Issue #665: Error classification patterns for _classify_command_error
# Format: (pattern_list, message_template, suggestion)
# pattern_list contains strings to check in combined error/stderr
_REPAIRABLE_ERROR_PATTERNS = (
    (
        ["no such file or directory", "file not found"],
        "File not found: {error}",
        "Create the file first, or check if the path exists using 'ls'",
    ),
    (
        ["permission denied", "access denied"],
        "Permission denied: {error}",
        "Try using sudo, or execute from a different directory with proper permissions",
    ),
    (
        ["command not found", "not recognized"],
        "Command not found: {cmd_name}",
        "Install the package that provides '{cmd_name}', or use an alternative command",
    ),
    (
        ["timeout", "timed out"],
        "Command timed out: {command}",
        "Break the operation into smaller steps, or increase the timeout",
    ),
    (
        ["connection refused", "network unreachable"],
        "Connection error: {error}",
        "Check network connectivity, verify the target host is running, and retry",
    ),
    (
        ["syntax error", "unexpected token"],
        "Syntax error in command: {error}",
        "Check the command syntax and escape special characters properly",
    ),
    (
        ["is a directory", "not a directory"],
        "Directory error: {error}",
        "Use the correct path type (file vs directory) for this operation",
    ),
    (
        ["no space left", "disk full"],
        "Disk space error: {error}",
        "Free up disk space by removing unnecessary files, then retry",
    ),
)

# Critical error patterns that should NOT be repairable
_CRITICAL_ERROR_PATTERNS = ["out of memory", "cannot allocate"]


def _match_repairable_error(
    combined: str, command: str, error: str
) -> RepairableException | None:
    """Match error against repairable patterns (Issue #665: extracted helper).

    Args:
        combined: Lowercase combined error and stderr text
        command: The original command that failed
        error: Original error message

    Returns:
        RepairableException if a pattern matches, None otherwise
    """
    from src.utils.errors import RepairableException

    cmd_name = command.split()[0] if command else "command"
    format_vars = {"error": error, "cmd_name": cmd_name, "command": command}

    for patterns, message_template, suggestion in _REPAIRABLE_ERROR_PATTERNS:
        if any(p in combined for p in patterns):
            return RepairableException(
                message=message_template.format(**format_vars),
                suggestion=suggestion.format(**format_vars),
            )
    return None


def _create_execution_result(
    command: str, host: str, result: Dict[str, Any], approved: bool = False
) -> Dict[str, Any]:
    """Create standardized execution result record (Issue #315: extracted).

    Args:
        command: The command that was executed
        host: Target host
        result: Execution result dict
        approved: Whether user approved the command

    Returns:
        Standardized execution result dict for continuation loop
    """
    return {
        "command": command,
        "host": host,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "return_code": result.get("return_code", 0),
        "status": "success",
        "approved": approved,
    }


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
            logger.error("Failed to initialize terminal tool: %s", e)
            self.terminal_tool = None

    def _parse_tool_calls(
        self, text: str, is_first_iteration: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response using XML-style markers.

        Issue #620: Refactored to use helper functions.
        Issue #650: Fixed regex to handle nested JSON in params.
        Issue #716: Enforces single tool call per iteration and plan-first execution.

        Args:
            text: LLM response text
            is_first_iteration: Whether this is the first iteration

        Returns:
            List containing at most ONE tool call dictionary (single-step execution)
        """
        logger.debug(
            "[_parse_tool_calls] Searching for TOOL_CALL markers in text of length %d",
            len(text),
        )
        text = html.unescape(text)
        has_tool_call, has_planning = self._detect_tool_call_markers(text)

        if self._should_defer_for_planning(
            is_first_iteration, has_planning, has_tool_call
        ):
            return []

        tool_calls, match_count = self._extract_tool_calls_from_text(text)
        self._log_parsing_result(
            tool_calls,
            match_count,
            has_tool_call,
            is_first_iteration,
            has_planning,
            text,
        )
        return tool_calls

    def _detect_tool_call_markers(self, text: str) -> tuple[bool, bool]:
        """Detect presence of tool call and planning markers. Issue #620."""
        has_tool_call = ("<TOOL_CALL" in text) or ("<tool_call" in text)
        has_planning = "[PLANNING]" in text or "[planning]" in text.lower()
        logger.debug(
            "[_parse_tool_calls] has_tool_call=%s, has_planning=%s",
            has_tool_call,
            has_planning,
        )
        return has_tool_call, has_planning

    def _should_defer_for_planning(
        self, is_first_iteration: bool, has_planning: bool, has_tool_call: bool
    ) -> bool:
        """Check if execution should be deferred to show plan first. Issue #716, #620."""
        if is_first_iteration and has_planning and has_tool_call:
            logger.info(
                "[Issue #716] Plan-first execution: First iteration with planning block detected. "
                "Deferring tool execution to show plan first."
            )
            return True
        return False

    def _extract_tool_calls_from_text(
        self, text: str
    ) -> tuple[List[Dict[str, Any]], int]:
        """Extract tool calls using regex pattern. Issue #650, #620."""
        tool_calls = []
        match_count = 0
        for match in _TOOL_CALL_PATTERN.finditer(text):
            match_count += 1
            tool_name = match.group(1)
            params_str = match.group(3)
            description = match.group(4).strip()
            try:
                params = json.loads(params_str)
                tool_calls.append(
                    {"name": tool_name, "params": params, "description": description}
                )
                logger.debug(
                    "[_parse_tool_calls] Found TOOL_CALL #%d: name=%s",
                    match_count,
                    tool_name,
                )
                # Issue #716: Only process ONE execute_command per iteration
                if tool_name == "execute_command":
                    logger.info(
                        "[Issue #716] Single-step execution enforced: returning first execute_command"
                    )
                    break
            except json.JSONDecodeError as e:
                logger.error("Failed to parse tool call params: %s", e)
                logger.error(
                    "Params string (first 200 of %d chars): %s",
                    len(params_str),
                    params_str[:200],
                )
        return tool_calls, match_count

    def _log_parsing_result(
        self,
        tool_calls: List,
        match_count: int,
        has_tool_call: bool,
        is_first_iteration: bool,
        has_planning: bool,
        text: str,
    ) -> None:
        """Log parsing results and warnings. Issue #650, #620."""
        logger.info(
            "[_parse_tool_calls] Total matches: %d, returning: %d",
            match_count,
            len(tool_calls),
        )
        if (
            not tool_calls
            and has_tool_call
            and not (is_first_iteration and has_planning)
        ):
            logger.warning(
                "[Issue #650] TOOL_CALL tag found but regex didn't match! Snippet: %s",
                text[:500],
            )

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
                "✅ Persisted approval request immediately: session=%s, terminal=%s",
                session_id,
                terminal_session_id,
            )
        except Exception as persist_error:
            logger.error(
                "Failed to persist approval request immediately: %s",
                persist_error,
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
        comment = last_command.get("approval_comment") or last_command.get(
            "denial_reason"
        )
        status_msg = {
            "approval_status": approval_status,
            "approval_comment": comment,
        }

        return approval_result, status_msg, True

    def _build_approval_request_message(
        self,
        session_id: str,
        command: str,
        result: Dict[str, Any],
        terminal_session_id: str,
        description: str,
    ) -> WorkflowMessage:
        """Build the approval request WorkflowMessage."""
        return WorkflowMessage(
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

    def _build_waiting_message(
        self, command: str, result: Dict[str, Any]
    ) -> WorkflowMessage:
        """Build the waiting for approval WorkflowMessage."""
        return WorkflowMessage(
            type="response",
            content=(
                f"\n\n⏳ Waiting for your approval to execute: `{command}`\n"
                f"Risk level: {result.get('risk')}\n"
                f"Reasons: {', '.join(result.get('reasons', []))}\n"
            ),
            metadata={"message_type": "approval_waiting", "command": command},
        )

    async def _poll_for_approval(
        self,
        terminal_session_id: str,
        command: str,
        max_wait_time: int = 3600,
        poll_interval: float = 0.5,
    ):
        """
        Poll for approval status until approved/denied or timeout.

        Yields:
            Tuple of (approval_result, status_msg) when found, None while waiting
        """
        elapsed_time = 0
        poll_count = 0

        while elapsed_time < max_wait_time:
            await asyncio.sleep(poll_interval)
            elapsed_time += poll_interval
            poll_count += 1

            try:
                session_info = await self.terminal_tool.get_session_info(
                    terminal_session_id
                )

                if poll_count % 20 == 0:
                    pending = (
                        session_info.get("pending_approval") is not None
                        if session_info
                        else "NO SESSION"
                    )
                    logger.info(
                        "🔍 [APPROVAL POLLING] Still waiting... (elapsed: %.1fs, pending: %s)",
                        elapsed_time,
                        pending,
                    )

                result_data, status_msg, should_break = self._check_approval_completion(
                    session_info, command, elapsed_time, max_wait_time
                )

                if should_break:
                    yield (result_data, status_msg)
                    return

            except Exception as check_error:
                logger.error("Error checking approval status: %s", check_error)

        yield (None, None)  # Timeout

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

        Yields:
            WorkflowMessage for approval request and status updates
        Returns:
            Approval result dict or None if timeout
        """
        approval_msg = self._build_approval_request_message(
            session_id, command, result, terminal_session_id, description
        )
        yield approval_msg

        await self._persist_approval_request(
            approval_msg, session_id, terminal_session_id
        )
        yield self._build_waiting_message(command, result)

        logger.info("🔍 [APPROVAL POLLING] Waiting for approval of command: %s", command)
        logger.info(
            "🔍 [APPROVAL POLLING] Chat session: %s, Terminal session: %s",
            session_id,
            terminal_session_id,
        )

        async for poll_result in self._poll_for_approval(terminal_session_id, command):
            approval_result, status_msg = poll_result
            if approval_result:
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
            yield approval_result

    async def _handle_approved_command(
        self,
        command: str,
        host: str,
        approval_result: Dict[str, Any],
        ollama_endpoint: str,
        selected_model: str,
    ):
        """Issue #665: Extracted from _handle_approval_workflow to reduce function length.

        Handle successful command approval - execute and interpret results.

        Yields:
            WorkflowMessage for execution status
            Tuple of (exec_result, additional_text) as final item
        """
        exec_result = _create_execution_result(
            command, host, approval_result, approved=True
        )
        additional_text = ""

        yield WorkflowMessage(
            type="response",
            content="\n\n✅ Command approved and executed! Interpreting results...\n\n",
            metadata={
                "message_type": "command_executed",
                "command": command,
                "executed": True,
                "approved": True,
            },
        )

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
                additional_text += interp_chunk.content

        yield (exec_result, additional_text)

    def _handle_approval_failure(
        self, command: str, approval_result: Dict[str, Any] | None
    ) -> tuple[WorkflowMessage, str]:
        """Issue #665: Extracted from _handle_approval_workflow to reduce function length.

        Handle approval denial or timeout.

        Returns:
            Tuple of (WorkflowMessage, additional_text)
        """
        if approval_result:
            error = approval_result.get("error", "Command was denied or failed")
            return (
                WorkflowMessage(
                    type="error",
                    content=f"Command execution failed: {error}",
                    metadata={"command": command, "error": True},
                ),
                f"\n\n❌ {error}",
            )
        else:
            return (
                WorkflowMessage(
                    type="error",
                    content=f"Approval timeout for command: {command}",
                    metadata={"command": command, "timeout": True},
                ),
                f"\n\n⏱️ Approval timeout for command: {command}",
            )

    async def _handle_approval_workflow(
        self,
        session_id: str,
        command: str,
        host: str,
        result: Dict[str, Any],
        terminal_session_id: str,
        description: str,
        ollama_endpoint: str,
        selected_model: str,
    ):
        """Handle command requiring approval (Issue #315: extracted).

        Yields:
            WorkflowMessage for approval stages
            Tuple of (exec_result, additional_text) as final item
        """
        approval_result = None
        async for approval_msg in self._handle_pending_approval(
            session_id, command, result, terminal_session_id, description
        ):
            if isinstance(approval_msg, dict):
                approval_result = approval_msg
            else:
                yield approval_msg

        if approval_result and approval_result.get("status") == "success":
            async for msg in self._handle_approved_command(
                command, host, approval_result, ollama_endpoint, selected_model
            ):
                yield msg
        else:
            error_msg, additional_text = self._handle_approval_failure(
                command, approval_result
            )
            yield error_msg
            yield (None, additional_text)

    async def _handle_direct_execution(
        self,
        command: str,
        host: str,
        result: Dict[str, Any],
        ollama_endpoint: str,
        selected_model: str,
    ):
        """Handle direct command execution without approval (Issue #315: extracted).

        Yields:
            WorkflowMessage for interpretation
            Tuple of (exec_result, additional_text) as final item
        """
        exec_result = _create_execution_result(command, host, result, approved=False)

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
            yield msg

        # Issue #651: Removed duplicate WorkflowMessage yield - interpretation was already
        # yielded in the loop above. Only yield the tuple for the continuation loop.
        yield (exec_result, f"\n\n{interpretation}")

    async def _collect_workflow_results(
        self, workflow_gen, execution_results: List, additional_response_parts: List
    ):
        """Collect results from workflow generator (Issue #315: extracted).

        Args:
            workflow_gen: Async generator from workflow handler
            execution_results: List to append exec results to
            additional_response_parts: List to append text parts to

        Yields:
            WorkflowMessage items from the generator
        """
        async for msg in workflow_gen:
            if isinstance(msg, tuple):
                exec_result, add_text = msg
                if exec_result:
                    execution_results.append(exec_result)
                additional_response_parts.append(add_text)
            elif msg is not None:
                # Issue #680: Only yield non-None WorkflowMessage objects
                yield msg

    async def _process_single_command(
        self,
        tool_call: Dict[str, Any],
        session_id: str,
        terminal_session_id: str,
        ollama_endpoint: str,
        selected_model: str,
        execution_results: List,
        additional_response_parts: List,
    ):
        """Process a single execute_command tool call (Issue #315: extracted).

        Issue #655: Now wraps common errors as RepairableException to allow
        LLM to retry with a different approach.

        Yields:
            WorkflowMessage items
        """
        command = tool_call["params"].get("command")
        host = tool_call["params"].get("host", "main")
        description = tool_call.get("description", "")

        logger.info("[ChatWorkflowManager] Executing command: %s on %s", command, host)

        result = await self._execute_terminal_command(
            session_id=session_id, command=command, host=host, description=description
        )

        if result.get("status") == "pending_approval":
            if not terminal_session_id:
                logger.error(
                    "No terminal session found for conversation %s", session_id
                )
                yield WorkflowMessage(
                    type="error",
                    content="Terminal session error - cannot request approval",
                    metadata={"error": True},
                )
                return

            workflow_gen = self._handle_approval_workflow(
                session_id,
                command,
                host,
                result,
                terminal_session_id,
                description,
                ollama_endpoint,
                selected_model,
            )
            async for msg in self._collect_workflow_results(
                workflow_gen, execution_results, additional_response_parts
            ):
                yield msg

        elif result.get("status") == "success":
            workflow_gen = self._handle_direct_execution(
                command, host, result, ollama_endpoint, selected_model
            )
            async for msg in self._collect_workflow_results(
                workflow_gen, execution_results, additional_response_parts
            ):
                yield msg

        elif result.get("status") == "error":
            async for msg in self._handle_command_error(
                command, result, additional_response_parts
            ):
                yield msg

    async def _handle_command_error(
        self,
        command: str,
        result: Dict[str, Any],
        additional_response_parts: List,
    ):
        """Handle command execution error (Issue #665: extracted helper).

        Classifies error as repairable or critical and yields appropriate message.

        Args:
            command: The command that failed
            result: Execution result dict with error/stderr
            additional_response_parts: List to append context to

        Yields:
            WorkflowMessage with error details
        """
        error = result.get("error", "Unknown error")
        stderr = result.get("stderr", "")
        repairable_error = self._classify_command_error(command, error, stderr)

        if repairable_error:
            logger.info(
                "[Issue #655] Repairable error for command '%s': %s",
                command,
                repairable_error.message,
            )
            additional_response_parts.append(f"\n\n{repairable_error.to_llm_context()}")
            yield WorkflowMessage(
                type="error",
                content=repairable_error.to_llm_context(),
                metadata={
                    "command": command,
                    "error": True,
                    "repairable": True,
                    "suggestion": repairable_error.suggestion,
                },
            )
        else:
            additional_response_parts.append(f"\n\n❌ Command execution failed: {error}")
            yield WorkflowMessage(
                type="error",
                content=f"Command failed: {error}",
                metadata={"command": command, "error": True, "repairable": False},
            )

    def _classify_command_error(
        self, command: str, error: str, stderr: str
    ) -> RepairableException | None:
        """
        Classify command execution error as repairable or critical.

        Issue #655: Analyzes error message and stderr to determine if LLM
        can potentially fix the issue by trying a different approach.
        Issue #665: Refactored to use _match_repairable_error helper and
        module-level pattern constants for maintainability.

        Args:
            command: The command that failed
            error: Error message
            stderr: Standard error output

        Returns:
            RepairableException if error is recoverable, None if critical
        """
        combined = f"{error.lower()} {stderr.lower()}"

        # Check for critical (non-repairable) errors first
        if any(p in combined for p in _CRITICAL_ERROR_PATTERNS):
            logger.warning("[Issue #655] Critical error (out of memory): %s", error)
            return None

        # Check against repairable error patterns
        result = _match_repairable_error(combined, command, error)
        if result:
            return result

        # Default: treat as repairable with generic suggestion
        return RepairableException(
            message=f"Command failed: {error}",
            suggestion="Check the error details and try an alternative approach",
        )

    def _handle_respond_tool(
        self, tool_call: Dict[str, Any]
    ) -> tuple[WorkflowMessage, bool, str]:
        """
        Handle the 'respond' tool for explicit task completion.

        Issue #665: Extracted from _process_tool_calls for single responsibility.
        Issue #654: Original respond tool handling logic.

        Returns:
            Tuple of (message, break_loop_requested, respond_content)
        """
        params = tool_call.get("params", {})
        respond_content = params.get("text", params.get("content", ""))
        break_loop_requested = params.get("break_loop", True)

        logger.info(
            "[Issue #654] Respond tool invoked: break_loop=%s, content_len=%d",
            break_loop_requested,
            len(respond_content),
        )

        message = WorkflowMessage(
            type="response",
            content=respond_content,
            metadata={
                "message_type": "respond_tool",
                "break_loop": break_loop_requested,
                "explicit_completion": True,
            },
        )

        return message, break_loop_requested, respond_content

    def _handle_delegate_tool(
        self, tool_call: Dict[str, Any], execution_results: List[Dict[str, Any]]
    ) -> WorkflowMessage:
        """
        Handle the 'delegate' tool for subordinate agent delegation.

        Issue #665: Extracted from _process_tool_calls for single responsibility.
        Issue #657: Original delegate tool handling logic.

        Returns:
            WorkflowMessage for delegation status
        """
        params = tool_call.get("params", {})
        task = params.get("task", "")
        reason = params.get("reason", "Task delegation")
        wait_for_result = params.get("wait_for_result", True)

        logger.info(
            "[Issue #657] Delegate tool invoked: task=%s, reason=%s", task[:100], reason
        )

        # Record delegation for manager to process
        execution_results.append(
            {
                "tool": "delegate",
                "task": task,
                "reason": reason,
                "wait_for_result": wait_for_result,
                "status": "pending_delegation",
            }
        )

        return WorkflowMessage(
            type="delegation",
            content=f"Delegating subtask: {task[:100]}...",
            metadata={
                "message_type": "delegate_tool",
                "reason": reason,
                "task": task,
            },
        )

    async def _process_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        session_id: str,
        terminal_session_id: str,
        ollama_endpoint: str,
        selected_model: str,
    ):
        """Process all tool calls from LLM response.

        Issue #315: Refactored to use helper methods for reduced nesting.
        Issue #654: Added support for 'respond' tool with break_loop pattern.
        Issue #665: Refactored to extract tool-specific handlers.

        Yields:
            WorkflowMessage for each stage of execution
            Also yields execution_summary at end for Issue #352 continuation loop
            Finally yields (break_loop, response_content) tuple if respond tool used
        """
        execution_results = []
        additional_response_parts = []
        break_loop_requested = False
        respond_content = None

        for tool_call in tool_calls:
            tool_name = tool_call["name"]

            if tool_name == "respond":
                msg, break_loop_requested, respond_content = self._handle_respond_tool(
                    tool_call
                )
                yield msg
                continue

            if tool_name == "delegate":
                yield self._handle_delegate_tool(tool_call, execution_results)
                continue

            if tool_name != "execute_command":
                logger.debug(
                    "[_process_tool_calls] Skipping unknown tool: %s", tool_name
                )
                continue

            async for msg in self._process_single_command(
                tool_call,
                session_id,
                terminal_session_id,
                ollama_endpoint,
                selected_model,
                execution_results,
                additional_response_parts,
            ):
                yield msg

        if execution_results:
            yield WorkflowMessage(
                type="execution_summary",
                content="",
                metadata={
                    "execution_results": execution_results,
                    "total_commands": len(execution_results),
                    "successful_commands": sum(
                        1 for r in execution_results if r.get("status") == "success"
                    ),
                },
            )

        # Issue #654: Yield break_loop signal as final item
        yield (break_loop_requested, respond_content)
