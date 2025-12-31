# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Step Executor Agent

Executes a single task/step and provides explanations.
Handles streaming output for long-running commands (like nmap).

Flow for each step:
1. Generate Part 1 explanation (what the command does)
2. Execute the command with streaming output
3. Wait for command completion
4. Generate Part 2 explanation (what the output shows)
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import AsyncGenerator, Optional, Union

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

logger = logging.getLogger(__name__)


class StepExecutorAgent:
    """
    Executes a single task and provides two-part explanations.

    Handles:
    - Command explanation generation (Part 1)
    - Command execution with streaming output
    - Output explanation generation (Part 2)
    """

    def __init__(
        self,
        session_id: str,
        explanation_service: Optional[CommandExplanationService] = None,
    ):
        """
        Initialize the StepExecutorAgent.

        Args:
            session_id: The chat session ID
            explanation_service: Optional custom explanation service
        """
        self.session_id = session_id
        self.explanation_service = (
            explanation_service or get_command_explanation_service()
        )
        self._command_executor = None

    async def _get_command_executor(self):
        """Get or create the command executor."""
        if self._command_executor is None:
            try:
                from backend.services.agent_terminal.command_executor import (
                    CommandExecutor,
                )

                self._command_executor = CommandExecutor()
            except ImportError:
                logger.warning("CommandExecutor not available, using subprocess fallback")
                self._command_executor = None
        return self._command_executor

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

        # If no command, just return a completed status
        if not task.command:
            yield StepResult(
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
                execution_time=time.time() - start_time,
            )
            return

        # Phase 1: Generate command explanation BEFORE execution
        command_explanation = await self._generate_command_explanation(task.command)

        # Yield initial update with command explanation
        yield StreamChunk(
            task_id=task.task_id,
            step_number=task.step_number,
            chunk_type="command_explanation",
            content="",  # Content is in the command_explanation field
            is_final=False,
        )

        # Phase 2: Execute command with streaming output
        task.status = StepStatus.STREAMING
        output_buffer = []
        return_code = 0

        try:
            async for chunk in self._execute_command_streaming(task.command):
                output_buffer.append(chunk.content)
                yield chunk

                # Check if this is the final chunk
                if chunk.is_final:
                    # Extract return code if provided
                    if chunk.chunk_type == "return_code":
                        try:
                            return_code = int(chunk.content)
                        except ValueError:
                            pass

        except Exception as e:
            logger.error("[StepExecutor] Command execution failed: %s", e)
            task.status = StepStatus.FAILED
            task.error = str(e)

            yield StepResult(
                task_id=task.task_id,
                step_number=task.step_number,
                total_steps=task.total_steps,
                status=StepStatus.FAILED,
                command=task.command,
                command_explanation=command_explanation,
                output=f"Error: {e}",
                output_explanation=None,
                return_code=-1,
                execution_time=time.time() - start_time,
                error=str(e),
            )
            return

        # Combine all output
        full_output = "".join(output_buffer)

        # Phase 3: Generate output explanation AFTER completion
        task.status = StepStatus.EXPLAINING
        output_explanation = await self._generate_output_explanation(
            task.command, full_output, return_code
        )

        # Mark complete
        task.status = StepStatus.COMPLETED
        task.completed_at = datetime.now()

        # Yield final result with both explanations
        yield StepResult(
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

        logger.info(
            "[StepExecutor] Completed step %d/%d in %.2fs",
            task.step_number,
            task.total_steps,
            time.time() - start_time,
        )

    async def _generate_command_explanation(
        self, command: str
    ) -> CommandExplanation:
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

    async def _execute_command_streaming(
        self, command: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Execute a command and stream its output.

        Uses asyncio subprocess for streaming.
        """
        logger.info("[StepExecutor] Executing command: %s", command[:100])

        try:
            # Use asyncio subprocess for streaming
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Create task ID for chunks
            task_id = f"exec_{id(process)}"

            # Stream stdout
            async def stream_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    yield StreamChunk(
                        task_id=task_id,
                        step_number=0,  # Will be overwritten by caller
                        chunk_type="stdout",
                        content=line.decode("utf-8", errors="replace"),
                        is_final=False,
                    )

            # Stream stderr
            async def stream_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    yield StreamChunk(
                        task_id=task_id,
                        step_number=0,
                        chunk_type="stderr",
                        content=line.decode("utf-8", errors="replace"),
                        is_final=False,
                    )

            # Interleave stdout and stderr
            stdout_task = asyncio.create_task(self._collect_stream(stream_stdout()))
            stderr_task = asyncio.create_task(self._collect_stream(stream_stderr()))

            # Yield chunks as they come
            stdout_chunks, stderr_chunks = await asyncio.gather(
                stdout_task, stderr_task
            )

            # Yield all stdout chunks
            for chunk in stdout_chunks:
                yield chunk

            # Yield all stderr chunks
            for chunk in stderr_chunks:
                yield chunk

            # Wait for process to complete
            return_code = await process.wait()

            # Yield return code as final chunk
            yield StreamChunk(
                task_id=task_id,
                step_number=0,
                chunk_type="return_code",
                content=str(return_code),
                is_final=True,
            )

        except Exception as e:
            logger.error("[StepExecutor] Command execution error: %s", e)
            yield StreamChunk(
                task_id="error",
                step_number=0,
                chunk_type="error",
                content=str(e),
                is_final=True,
            )

    async def _collect_stream(
        self, stream: AsyncGenerator[StreamChunk, None]
    ) -> list:
        """Collect all chunks from a stream into a list."""
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        return chunks

    async def execute_simple(
        self, command: str
    ) -> StepResult:
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
