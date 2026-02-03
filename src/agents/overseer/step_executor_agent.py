# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Step Executor Agent

Executes a single task/step and provides explanations.
Handles streaming output for long-running commands (like nmap).

Flow for each step:
1. Validate command safety
2. Generate Part 1 explanation (what the command does)
3. Execute the command in PTY terminal (visible to user)
4. Stream output in real-time
5. Generate Part 2 explanation (what the output shows)

Security: Commands are validated against dangerous patterns before execution.
Execution: Uses PTY integration for commands to appear in user's terminal.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import AsyncGenerator, Optional, Tuple, Union

from src.security.command_patterns import check_dangerous_patterns, is_safe_command
from src.utils.command_utils import execute_shell_command_streaming

from .command_explanation_service import (
    CommandExplanationService,
    get_command_explanation_service,
)
from .types import (
    AgentTask,
    CommandExplanation,
    OutputExplanation,
    StepResult,
    StepStatus,
    StreamChunk,
)

# Import PTY manager for terminal integration
try:
    from backend.services.simple_pty import simple_pty_manager

    PTY_AVAILABLE = True
except ImportError:
    simple_pty_manager = None
    PTY_AVAILABLE = False

logger = logging.getLogger(__name__)

# Issue #765: DANGEROUS_PATTERNS and SAFE_COMMANDS now imported from
# src.security.command_patterns for centralized security pattern management


def _build_no_command_result(task: "AgentTask", execution_time: float) -> StepResult:
    """
    Build StepResult for steps with no command to execute.

    Issue #665: Extracted from execute_step to reduce function length.
    """
    return StepResult(
        task_id=task.task_id,
        step_number=task.step_number,
        total_steps=task.total_steps,
        status=StepStatus.COMPLETED,
        command=None,
        command_explanation=None,
        output="No command to execute for this step.",
        output_explanation=OutputExplanation(
            summary="This step did not require command execution.",
            key_findings=[task.description],
        ),
        execution_time=execution_time,
    )


def _build_blocked_command_result(
    task: "AgentTask", safety_reason: Optional[str], execution_time: float
) -> StepResult:
    """
    Build StepResult for commands blocked by security validation.

    Issue #665: Extracted from execute_step to reduce function length.
    """
    return StepResult(
        task_id=task.task_id,
        step_number=task.step_number,
        total_steps=task.total_steps,
        status=StepStatus.FAILED,
        command=task.command,
        command_explanation=None,
        output=f"Command blocked: {safety_reason}",
        output_explanation=OutputExplanation(
            summary="This command was blocked for security reasons.",
            key_findings=[safety_reason or "Dangerous operation detected"],
        ),
        return_code=-1,
        execution_time=execution_time,
        error=safety_reason,
    )


def _build_execution_error_result(
    task: "AgentTask", error: Exception, execution_time: float
) -> StepResult:
    """
    Build StepResult for command execution failures.

    Issue #665: Extracted from execute_step to reduce function length.
    """
    return StepResult(
        task_id=task.task_id,
        step_number=task.step_number,
        total_steps=task.total_steps,
        status=StepStatus.FAILED,
        command=task.command,
        command_explanation=None,
        output=f"Error: {error}",
        output_explanation=None,
        return_code=-1,
        execution_time=execution_time,
        error=str(error),
    )


class StepExecutorAgent:
    """
    Executes a single task and provides two-part explanations.

    Handles:
    - Command explanation generation (Part 1)
    - Command execution in PTY terminal (visible to user)
    - Output explanation generation (Part 2)
    """

    def __init__(
        self,
        session_id: str,
        pty_session_id: Optional[str] = None,
        explanation_service: Optional[CommandExplanationService] = None,
    ):
        """
        Initialize the StepExecutorAgent.

        Args:
            session_id: The chat session ID (conversation_id)
            pty_session_id: PTY session ID for terminal execution (usually same as session_id)
            explanation_service: Optional custom explanation service
        """
        self.session_id = session_id
        # PTY session ID is usually the conversation_id
        self.pty_session_id = pty_session_id or session_id
        self.explanation_service = (
            explanation_service or get_command_explanation_service()
        )
        self._command_executor = None
        self._chat_history_manager = None

    def _validate_command(self, command: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a command for safety before execution.

        Issue #765: Uses centralized patterns from src.security.command_patterns.

        Args:
            command: The shell command to validate

        Returns:
            Tuple of (is_safe, reason_if_unsafe)
        """
        if not command or not command.strip():
            return False, "Empty command"

        # Extract base command
        parts = command.strip().split()
        if not parts:
            return False, "Empty command"

        base_cmd = parts[0].split("/")[-1]  # Handle full paths like /usr/bin/ls

        # Check against dangerous patterns using centralized function (Issue #765)
        dangerous_matches = check_dangerous_patterns(command)
        if dangerous_matches:
            # Return the first match's description
            reason = dangerous_matches[0][0]
            logger.warning(
                "[StepExecutor] BLOCKED dangerous command: %s (reason: %s)",
                command[:50],
                reason,
            )
            return False, f"Blocked for security: {reason}"

        # Check if base command is in safe list using centralized function (Issue #765)
        if not is_safe_command(base_cmd):
            # Log but allow - user can decide
            logger.info(
                "[StepExecutor] Command '%s' not in safe list, proceeding with caution",
                base_cmd,
            )

        return True, None

    async def _get_command_executor(self):
        """Get or create the command executor."""
        if self._command_executor is None:
            try:
                from backend.services.agent_terminal.command_executor import (
                    CommandExecutor,
                )

                self._command_executor = CommandExecutor()
            except ImportError:
                logger.warning(
                    "CommandExecutor not available, using subprocess fallback"
                )
                self._command_executor = None
        return self._command_executor

    async def _execute_and_stream_command(
        self, task: AgentTask
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Execute command and stream output chunks.

        Issue #665: Extracted from execute_step to reduce function length.

        Args:
            task: The task containing the command to execute

        Yields:
            StreamChunk objects during execution
        """
        # Notify that execution is starting
        yield StreamChunk(
            task_id=task.task_id,
            step_number=task.step_number,
            chunk_type="execution_start",
            content=f"Executing: {task.command}",
            is_final=False,
        )

        async for chunk in self._execute_command_streaming(task.command):
            yield chunk

    async def _generate_explanations_for_result(
        self, task: AgentTask, full_output: str, return_code: int
    ) -> tuple[CommandExplanation, OutputExplanation]:
        """
        Generate both command and output explanations after execution.

        Issue #665: Extracted from execute_step to reduce function length.

        Args:
            task: The task that was executed
            full_output: The complete output from command execution
            return_code: The command's return code

        Returns:
            Tuple of (command_explanation, output_explanation)
        """
        # Notify that we're generating explanations
        task.status = StepStatus.EXPLAINING

        # Generate BOTH explanations AFTER execution
        command_explanation = await self._generate_command_explanation(task.command)
        output_explanation = await self._generate_output_explanation(
            task.command, full_output, return_code
        )

        return command_explanation, output_explanation

    def _extract_return_code_from_chunk(
        self, chunk: StreamChunk, current_code: int
    ) -> int:
        """
        Extract return code from a final chunk if available.

        Issue #665: Extracted from execute_step to reduce inline complexity.

        Args:
            chunk: The stream chunk to check
            current_code: Current return code value

        Returns:
            Updated return code
        """
        if chunk.is_final and chunk.chunk_type == "return_code":
            try:
                return int(chunk.content)
            except ValueError:
                pass
        return current_code

    def _create_explaining_notification(self, task: AgentTask) -> StreamChunk:
        """
        Create a notification chunk for explanation phase.

        Issue #665: Extracted from execute_step to reduce function length.

        Args:
            task: The task being executed

        Returns:
            StreamChunk for explaining notification
        """
        return StreamChunk(
            task_id=task.task_id,
            step_number=task.step_number,
            chunk_type="explaining",
            content="Generating explanations...",
            is_final=False,
        )

    async def _build_final_step_result(
        self,
        task: AgentTask,
        full_output: str,
        return_code: int,
        command_explanation: CommandExplanation,
        output_explanation: OutputExplanation,
        start_time: float,
    ) -> StepResult:
        """
        Build the final StepResult with all explanations.

        Issue #665: Extracted from execute_step to reduce function length.

        Args:
            task: The completed task
            full_output: The complete output from execution
            return_code: The command's return code
            command_explanation: The generated command explanation
            output_explanation: The generated output explanation
            start_time: The execution start time for calculating duration

        Returns:
            Complete StepResult with all data
        """
        task.status = StepStatus.COMPLETED
        task.completed_at = datetime.now()

        return StepResult(
            task_id=task.task_id,
            step_number=task.step_number,
            total_steps=task.total_steps,
            status=StepStatus.COMPLETED,
            command=task.command,
            command_explanation=command_explanation,
            output=full_output,
            output_explanation=output_explanation,
            return_code=return_code,
            execution_time=time.time() - start_time,
            is_streaming=True,
            stream_complete=True,
        )

    async def execute_step(
        self, task: AgentTask
    ) -> AsyncGenerator[Union[StreamChunk, StepResult], None]:
        """
        Execute a single step with streaming output and explanations.

        Yields:
            StreamChunk objects during command execution
            StepResult when complete (with explanations)
        """
        start_time = time.time()
        task.status = StepStatus.RUNNING
        task.started_at = datetime.now()

        logger.info(
            "[StepExecutor] Starting step %d/%d: %s",
            task.step_number,
            task.total_steps,
            task.description,
        )

        # If no command, just return a completed status (Issue #665: uses helper)
        if not task.command:
            yield _build_no_command_result(task, time.time() - start_time)
            return

        # Security: Validate command before execution (Issue #665: uses helper)
        is_safe, safety_reason = self._validate_command(task.command)
        if not is_safe:
            task.status = StepStatus.FAILED
            task.error = safety_reason
            yield _build_blocked_command_result(
                task, safety_reason, time.time() - start_time
            )
            return

        # Phase 1: Execute command in terminal with streaming output
        task.status = StepStatus.STREAMING
        output_buffer = []
        return_code = 0

        try:
            # Issue #665: Uses helpers for command execution
            async for chunk in self._execute_and_stream_command(task):
                output_buffer.append(chunk.content)
                yield chunk
                return_code = self._extract_return_code_from_chunk(chunk, return_code)

        except Exception as e:
            # Issue #665: Uses helper for error result
            logger.error("[StepExecutor] Command execution failed: %s", e)
            task.status = StepStatus.FAILED
            task.error = str(e)
            yield _build_execution_error_result(task, e, time.time() - start_time)
            return

        full_output = "".join(output_buffer)

        # Phase 2: Generate explanations (Issue #665: uses helpers)
        yield self._create_explaining_notification(task)

        (
            command_explanation,
            output_explanation,
        ) = await self._generate_explanations_for_result(task, full_output, return_code)

        # Build and yield final result (Issue #665: uses helper)
        result = await self._build_final_step_result(
            task,
            full_output,
            return_code,
            command_explanation,
            output_explanation,
            start_time,
        )
        yield result

        logger.info(
            "[StepExecutor] Completed step %d/%d in %.2fs",
            task.step_number,
            task.total_steps,
            time.time() - start_time,
        )

    async def _generate_command_explanation(self, command: str) -> CommandExplanation:
        """Generate Part 1: Command explanation."""
        try:
            return await self.explanation_service.explain_command(command)
        except Exception as e:
            logger.error("Failed to generate command explanation: %s", e)
            from .types import CommandBreakdownPart

            return CommandExplanation(
                summary=f"Executing: {command}",
                breakdown=[
                    CommandBreakdownPart(
                        part=command.split()[0] if command else "unknown",
                        explanation="Command",
                    )
                ],
            )

    async def _generate_output_explanation(
        self, command: str, output: str, return_code: int
    ) -> OutputExplanation:
        """Generate Part 2: Output explanation."""
        try:
            return await self.explanation_service.explain_output(
                command, output, return_code
            )
        except Exception as e:
            logger.error("Failed to generate output explanation: %s", e)
            return OutputExplanation(
                summary="Command completed."
                if return_code == 0
                else f"Command exited with code {return_code}.",
                key_findings=["See output above for details."],
            )

    async def _get_chat_history_manager(self):
        """Get or create chat history manager."""
        if self._chat_history_manager is None:
            try:
                from src.chat_history import ChatHistoryManager

                self._chat_history_manager = ChatHistoryManager()
            except ImportError:
                logger.warning("ChatHistoryManager not available")
        return self._chat_history_manager

    def _write_to_pty(self, text: str) -> bool:
        """
        Write text to PTY terminal.

        Args:
            text: Text to write (command + newline)

        Returns:
            True if written successfully
        """
        if not PTY_AVAILABLE or not simple_pty_manager:
            logger.warning("[StepExecutor] PTY not available")
            return False

        try:
            pty = simple_pty_manager.get_session(self.pty_session_id)

            if not pty or not pty.is_alive():
                logger.warning(
                    "[StepExecutor] PTY session %s not found or not alive",
                    self.pty_session_id,
                )
                # Try to create a new PTY session
                from src.constants.path_constants import PATH

                pty = simple_pty_manager.create_session(
                    self.pty_session_id, initial_cwd=str(PATH.PROJECT_ROOT)
                )
                if not pty:
                    logger.error("[StepExecutor] Failed to create PTY session")
                    return False
                logger.info(
                    "[StepExecutor] Created new PTY session %s", self.pty_session_id
                )

            success = pty.write_input(text)
            if success:
                logger.debug("[StepExecutor] Wrote to PTY: %s", text[:50])
            return success

        except Exception as e:
            logger.error("[StepExecutor] Error writing to PTY: %s", e)
            return False

    async def _execute_command_streaming(
        self, command: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Execute a command in PTY terminal and stream output.

        Uses PTY integration so commands appear in user's terminal.
        Output is polled from chat history (where WebSocket handler saves it).
        """
        logger.info("[StepExecutor] Executing command in PTY: %s", command[:100])
        task_id = f"exec_{self.pty_session_id}_{int(time.time())}"

        # Try PTY execution first (preferred - shows in user's terminal)
        if PTY_AVAILABLE and simple_pty_manager:
            # Write command to PTY
            if not self._write_to_pty(f"{command}\n"):
                logger.warning(
                    "[StepExecutor] PTY write failed, falling back to subprocess"
                )
            else:
                # Poll for output from chat history
                # The terminal WebSocket handler saves output to chat
                chat_manager = await self._get_chat_history_manager()
                if chat_manager:
                    yield StreamChunk(
                        task_id=task_id,
                        step_number=0,
                        chunk_type="pty_execution",
                        content=f"Executing: {command}",
                        is_final=False,
                    )

                    # Poll for output completion
                    output = await self._poll_pty_output(chat_manager, timeout=60.0)

                    # Yield final output
                    yield StreamChunk(
                        task_id=task_id,
                        step_number=0,
                        chunk_type="stdout",
                        content=output,
                        is_final=False,
                    )

                    # Yield return code (assume 0 for PTY execution)
                    # TODO: Detect actual return code from PTY
                    yield StreamChunk(
                        task_id=task_id,
                        step_number=0,
                        chunk_type="return_code",
                        content="0",
                        is_final=True,
                    )
                    return

        # Fallback: Use subprocess (output won't appear in user's terminal)
        logger.info("[StepExecutor] Using subprocess fallback for: %s", command[:50])
        async for chunk in self._execute_subprocess_streaming(command, task_id):
            yield chunk

    async def _poll_pty_output(
        self,
        chat_manager,
        timeout: float = 60.0,
        stability_threshold: float = 1.0,
    ) -> str:
        """
        Poll chat history for PTY output until stable.

        Args:
            chat_manager: ChatHistoryManager instance
            timeout: Maximum wait time
            stability_threshold: Seconds of unchanged output to consider stable

        Returns:
            Collected output from chat history
        """
        from src.utils.encoding_utils import strip_ansi_codes

        start_time = time.time()
        last_output = ""
        last_change_time = start_time
        poll_interval = 0.2

        logger.debug("[StepExecutor] Polling for PTY output (timeout=%ss)", timeout)

        while (time.time() - start_time) < timeout:
            try:
                messages = await chat_manager.get_session_messages(
                    session_id=self.session_id, limit=10
                )

                # Extract terminal output from recent messages
                current_output = ""
                for msg in reversed(messages):
                    if msg.get("sender") == "terminal" and msg.get("text"):
                        text = strip_ansi_codes(msg["text"])
                        if text and not text.startswith("$"):
                            current_output = text
                            break

                # Check stability
                if current_output and current_output == last_output:
                    stable_duration = time.time() - last_change_time
                    if stable_duration >= stability_threshold:
                        logger.info(
                            "[StepExecutor] Output stabilized after %.2fs",
                            time.time() - start_time,
                        )
                        return current_output
                elif current_output != last_output:
                    last_output = current_output
                    last_change_time = time.time()

            except Exception as e:
                logger.warning("[StepExecutor] Polling error: %s", e)

            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.2, 2.0)

        logger.warning("[StepExecutor] Polling timeout reached")
        return last_output

    async def _execute_subprocess_streaming(
        self, command: str, task_id: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Fallback: Execute command via subprocess (output won't appear in terminal UI).

        Issue #751: Uses centralized execute_shell_command_streaming from command_utils.
        """
        try:
            async for base_chunk in execute_shell_command_streaming(command):
                # Convert BaseStreamChunk to local StreamChunk with task context
                yield StreamChunk(
                    task_id=task_id,
                    step_number=0,
                    chunk_type=base_chunk.chunk_type,
                    content=base_chunk.content,
                    is_final=base_chunk.is_final,
                )

        except Exception as e:
            logger.error("[StepExecutor] Subprocess error: %s", e)
            yield StreamChunk(
                task_id="error",
                step_number=0,
                chunk_type="error",
                content=str(e),
                is_final=True,
            )

    async def _collect_stream(self, stream: AsyncGenerator[StreamChunk, None]) -> list:
        """Collect all chunks from a stream into a list."""
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        return chunks

    async def execute_simple(self, command: str) -> StepResult:
        """
        Execute a single command directly (non-streaming, for simple commands).

        Args:
            command: The command to execute

        Returns:
            StepResult with explanations
        """
        # Create a temporary task
        task = AgentTask(
            task_id=f"simple_{id(command)}",
            step_number=1,
            total_steps=1,
            description=f"Execute: {command}",
            command=command,
        )

        # Collect all results (non-streaming collection)
        result = None
        async for update in self.execute_step(task):
            if isinstance(update, StepResult):
                result = update

        return result
