# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Streaming Command Execution Module

This module provides real-time streaming command execution with intelligent
commentary and analysis for the intelligent agent system.
"""

import asyncio
import logging
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional

from backend.constants.network_constants import NetworkConstants
from backend.utils.command_validator import CommandValidator
from llm_interface import LLMInterface

logger = logging.getLogger(__name__)


class ChunkType(Enum):
    """Types of streaming chunks."""

    STATUS = "status"
    STDOUT = "stdout"
    STDERR = "stderr"
    COMMENTARY = "commentary"
    ERROR = "error"
    COMPLETE = "complete"
    # GUI toggle-compatible chunk types
    THOUGHT = "thought"
    PLANNING = "planning"
    DEBUG = "debug"
    UTILITY = "utility"
    JSON = "json"


@dataclass
class StreamChunk:
    """A chunk of streaming output."""

    timestamp: str
    chunk_type: ChunkType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessInfo:
    """Information about a running process."""

    process_id: str
    command: str
    pid: int
    start_time: float
    user_goal: str
    process: subprocess.Popen

    def get_runtime(self) -> float:
        """Get process runtime in seconds."""
        return time.time() - self.start_time


class StreamingCommandExecutor:
    """Real-time streaming command executor with intelligent commentary."""

    def __init__(
        self, llm_interface: LLMInterface, command_validator: CommandValidator
    ):
        """
        Initialize the streaming executor.

        Args:
            llm_interface: LLM interface for generating commentary
            command_validator: Command validator for security checks
        """
        self.llm_interface = llm_interface
        self.command_validator = command_validator
        self.active_processes: Dict[str, ProcessInfo] = {}
        self._max_processes = 10  # Limit concurrent processes

    def _validate_execution_preconditions(self, command: str) -> Optional[StreamChunk]:
        """Validate command safety and process limits. (Issue #315 - extracted)"""
        if not self.command_validator.is_command_safe(command):
            return StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.ERROR,
                content=f"❌ Command blocked by security policy: {command}",
                metadata={"security_blocked": True, "command": command},
            )
        if len(self.active_processes) >= self._max_processes:
            return StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.ERROR,
                content=(
                    "❌ Maximum number of concurrent processes "
                    f"({self._max_processes}) reached"
                ),
                metadata={"process_limit_reached": True},
            )
        return None

    def _parse_command_safe(
        self, command: str
    ) -> tuple[Optional[List[str]], Optional[StreamChunk]]:
        """Parse command safely, return (parts, error_chunk). (Issue #315 - extracted)"""
        try:
            return shlex.split(command), None
        except ValueError as e:
            return None, StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.ERROR,
                content=f"❌ Invalid command syntax: {str(e)}",
                metadata={"parse_error": True},
            )

    def _build_completion_chunk(
        self, return_code: int, execution_time: float, process_id: str
    ) -> StreamChunk:
        """Build a process completion chunk. (Issue #315 - extracted)"""
        if return_code == 0:
            return StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.COMPLETE,
                content=f"✅ Command completed successfully in {execution_time:.2f}s",
                metadata={
                    "success": True,
                    "return_code": return_code,
                    "execution_time": execution_time,
                    "process_id": process_id,
                },
            )
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.COMPLETE,
            content=f"⚠️ Command completed with exit code {return_code} in {execution_time:.2f}s",
            metadata={
                "success": False,
                "return_code": return_code,
                "execution_time": execution_time,
                "process_id": process_id,
            },
        )

    def _yield_text_lines_as_chunks(
        self, text: str, chunk_type: ChunkType, process_id: str
    ) -> List[StreamChunk]:
        """Convert text lines to stream chunks. (Issue #315 - extracted)"""
        chunks = []
        for line in text.split("\n"):
            if line.strip():  # Only yield non-empty lines
                chunks.append(
                    StreamChunk(
                        timestamp=self._get_timestamp(),
                        chunk_type=chunk_type,
                        content=line,
                        metadata={"process_id": process_id},
                    )
                )
        return chunks

    async def _terminate_process_safely(
        self, process: asyncio.subprocess.Process
    ) -> None:
        """Terminate process with graceful fallback to kill. (Issue #315 - extracted)"""
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()

    async def execute_with_streaming(
        self,
        command: str,
        user_goal: str,
        timeout: int = 300,
        provide_commentary: bool = True,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Issue #665: Refactored to use extracted helpers for reduced line count."""
        process_id = str(uuid.uuid4())
        start_time = time.time()
        logger.info("Executing command: %s (PID: %s)", command, process_id)

        if error := self._validate_execution_preconditions(command):
            yield error
            return

        try:
            yield self._create_status_chunk(command, process_id)
            cmd_parts, parse_error = self._parse_command_safe(command)
            if parse_error:
                yield parse_error
                return

            process = await self._start_process_and_track(
                cmd_parts, command, user_goal, process_id, start_time
            )
            async for chunk in self._execute_and_stream_output(
                process,
                process_id,
                command,
                user_goal,
                timeout,
                provide_commentary,
                start_time,
            ):
                yield chunk
        except Exception as e:
            yield self._create_startup_error_chunk(e)
        finally:
            self.active_processes.pop(process_id, None)

    async def _execute_and_stream_output(
        self,
        process: asyncio.subprocess.Process,
        process_id: str,
        command: str,
        user_goal: str,
        timeout: int,
        provide_commentary: bool,
        start_time: float,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Issue #665: Extracted from execute_with_streaming to reduce function length.

        Handle process output streaming, completion, and timeout handling.
        """
        try:
            await asyncio.wait_for(
                self._stream_process_output(
                    process, process_id, user_goal, provide_commentary
                ),
                timeout=timeout,
            )
            return_code = await process.wait()
            execution_time = time.time() - start_time
            yield self._build_completion_chunk(return_code, execution_time, process_id)

            if provide_commentary and return_code == 0:
                async for chunk in self._provide_completion_commentary(
                    command, user_goal, execution_time
                ):
                    yield chunk
        except asyncio.TimeoutError:
            yield self._create_timeout_error_chunk(timeout)
            await self._terminate_process_safely(process)
        except Exception as e:
            yield self._create_execution_error_chunk(e)

    async def _stream_process_output(
        self,
        process: asyncio.subprocess.Process,
        process_id: str,
        user_goal: str,
        provide_commentary: bool,
    ):
        """Issue #665: Refactored to use extracted stream reader helpers."""
        # Create stream context for shared state
        stream_ctx = {"stdout_buffer": "", "stderr_buffer": "", "commentary_counter": 0}

        # Create tasks for stdout and stderr reading
        tasks = [
            asyncio.create_task(
                self._collect_chunks(
                    self._read_stdout_stream(
                        process, process_id, user_goal, provide_commentary, stream_ctx
                    )
                )
            ),
            asyncio.create_task(
                self._collect_chunks(
                    self._read_stderr_stream(process, process_id, stream_ctx)
                )
            ),
        ]

        # Process completed tasks and yield chunks
        async for chunk in self._process_stream_tasks(tasks):
            yield chunk

    async def _read_stdout_stream(
        self,
        process: asyncio.subprocess.Process,
        process_id: str,
        user_goal: str,
        provide_commentary: bool,
        stream_ctx: Dict[str, Any],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Issue #665: Extracted from _stream_process_output to reduce function length.

        Async generator yielding stdout chunks with periodic commentary.
        """
        while True:
            try:
                data = await process.stdout.read(1024)
                if not data:
                    break

                text = data.decode("utf-8", errors="replace")
                stream_ctx["stdout_buffer"] += text

                for chunk in self._yield_text_lines_as_chunks(
                    text, ChunkType.STDOUT, process_id
                ):
                    yield chunk

                # Provide periodic commentary
                stream_ctx["commentary_counter"] += len(text)
                if provide_commentary and stream_ctx["commentary_counter"] > 500:
                    stream_ctx["commentary_counter"] = 0
                    async for chunk in self._provide_progress_commentary(
                        stream_ctx["stdout_buffer"][-200:], user_goal
                    ):
                        yield chunk

            except Exception as e:
                logger.warning("Error reading stdout: %s", e)
                break

    async def _read_stderr_stream(
        self,
        process: asyncio.subprocess.Process,
        process_id: str,
        stream_ctx: Dict[str, Any],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Issue #665: Extracted from _stream_process_output to reduce function length.

        Async generator yielding stderr chunks from process output.
        """
        while True:
            try:
                data = await process.stderr.read(1024)
                if not data:
                    break

                text = data.decode("utf-8", errors="replace")
                stream_ctx["stderr_buffer"] += text

                for chunk in self._yield_text_lines_as_chunks(
                    text, ChunkType.STDERR, process_id
                ):
                    yield chunk

            except Exception as e:
                logger.warning("Error reading stderr: %s", e)
                break

    async def _process_stream_tasks(
        self, tasks: List[asyncio.Task]
    ) -> AsyncGenerator[StreamChunk, None]:
        """Process stream tasks and yield chunks. (Issue #315 - extracted)

        Issue #509: Optimized O(n²) list.remove() to O(1) set operations.
        asyncio.wait() already returns sets, so we work directly with them.

        Issue #616: The nested loop (while → for done → for chunks) is O(tasks × chunks)
        which is optimal - we must yield each chunk from each completed task.
        """
        # Issue #509: Use set for O(1) removal instead of O(n) list.remove()
        remaining_tasks = set(tasks)
        try:
            while remaining_tasks:
                done, pending = await asyncio.wait(
                    remaining_tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    chunks = await self._safe_get_task_chunks(task)
                    for chunk in chunks:
                        yield chunk
                # Issue #509: O(1) set difference instead of O(n) list operations
                remaining_tasks = pending
        finally:
            for task in remaining_tasks:
                task.cancel()

    async def _safe_get_task_chunks(self, task: asyncio.Task) -> List[StreamChunk]:
        """Safely get chunks from completed task. (Issue #315 - extracted)"""
        try:
            return await task
        except Exception as e:
            logger.warning("Error in stream task: %s", e)
            return []

    # -------------------------------------------------------------------------
    # Issue #281 - Extracted helper methods for execute_with_streaming refactoring
    # -------------------------------------------------------------------------

    def _create_status_chunk(self, command: str, process_id: str) -> StreamChunk:
        """Create status chunk for command start (Issue #281 - extracted helper)."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.STATUS,
            content=f"🚀 Executing: {command}",
            metadata={"command": command, "process_id": process_id},
        )

    async def _start_process_and_track(
        self,
        cmd_parts: List[str],
        command: str,
        user_goal: str,
        process_id: str,
        start_time: float,
    ) -> asyncio.subprocess.Process:
        """Start async subprocess and track it (Issue #281 - extracted helper)."""
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )

        process_info = ProcessInfo(
            process_id=process_id,
            command=command,
            pid=process.pid,
            start_time=start_time,
            user_goal=user_goal,
            process=process,
        )
        self.active_processes[process_id] = process_info
        return process

    def _create_timeout_error_chunk(self, timeout: int) -> StreamChunk:
        """Create timeout error chunk (Issue #281 - extracted helper)."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.ERROR,
            content=f"⏰ Command timed out after {timeout}s",
            metadata={"timeout": True, "timeout_duration": timeout},
        )

    def _create_execution_error_chunk(self, error: Exception) -> StreamChunk:
        """Create execution error chunk (Issue #281 - extracted helper)."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.ERROR,
            content=f"❌ Execution error: {str(error)}",
            metadata={"execution_error": True, "error": str(error)},
        )

    def _create_startup_error_chunk(self, error: Exception) -> StreamChunk:
        """Create startup error chunk (Issue #281 - extracted helper)."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.ERROR,
            content=f"❌ Failed to start command: {str(error)}",
            metadata={"startup_error": True, "error": str(error)},
        )

    async def _collect_chunks(self, generator) -> List[StreamChunk]:
        """Collect chunks from async generator."""
        chunks = []
        try:
            async for chunk in generator:
                chunks.append(chunk)
                if len(chunks) >= 10:  # Limit batch size
                    break
        except Exception as e:
            logger.warning("Error collecting chunks: %s", e)
        return chunks

    async def _provide_progress_commentary(
        self, recent_output: str, user_goal: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Provide intelligent commentary on command progress."""
        try:
            # Skip if no meaningful output
            if not recent_output.strip():
                return

            # Create context-aware prompt
            prompt = (
                "Analyze this command output and provide a brief, helpful "
                "comment about the progress:\n\n"
                f"User Goal: {user_goal}\n"
                f"Recent Output: {recent_output[-150:]}\n\n"
                "Provide a single, concise comment (max 100 characters) "
                "about what's happening.\n"
                "Be helpful and informative, but don't repeat the obvious.\n"
                "Use emojis when appropriate.\n"
                "If the output is just routine/boring, respond with "
                "SKIP to avoid spam."
            )

            # Get LLM commentary
            response = await self.llm_interface.generate_response(
                prompt, temperature=0.7, max_tokens=50
            )

            # Skip if LLM suggests it
            if response.strip().upper() == "SKIP":
                return

            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.COMMENTARY,
                content=f"💭 {response.strip()}",
                metadata={"commentary_type": "progress"},
            )

        except Exception as e:
            logger.warning("Error generating progress commentary: %s", e)

    async def _provide_completion_commentary(
        self, command: str, user_goal: str, execution_time: float
    ) -> AsyncGenerator[StreamChunk, None]:
        """Provide intelligent commentary on command completion."""
        try:
            prompt = (
                "A command just completed successfully. "
                "Provide a brief, helpful summary:\n\n"
                f"User Goal: {user_goal}\n"
                f"Command: {command}\n"
                f"Execution Time: {execution_time:.2f}s\n\n"
                "Provide a single, concise comment (max 150 characters) "
                "summarizing what was accomplished.\n"
                "Be helpful and celebrate the success when appropriate.\n"
                "Use emojis when appropriate."
            )

            response = await self.llm_interface.generate_response(
                prompt, temperature=0.7, max_tokens=75
            )

            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.COMMENTARY,
                content=f"🎯 {response.strip()}",
                metadata={"commentary_type": "completion"},
            )

        except Exception as e:
            logger.warning("Error generating completion commentary: %s", e)

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from utils.command_utils import get_timestamp

        return get_timestamp()

    def get_active_processes(self) -> List[Dict[str, Any]]:
        """Get information about active processes."""
        return [
            {
                "process_id": info.process_id,
                "command": info.command,
                "pid": info.pid,
                "runtime": info.get_runtime(),
                "user_goal": info.user_goal,
            }
            for info in self.active_processes.values()
        ]

    async def kill_process(self, process_id: str) -> bool:
        """
        Kill a specific process.

        Args:
            process_id: Process identifier

        Returns:
            bool: True if process was killed successfully
        """
        if process_id not in self.active_processes:
            return False

        try:
            process_info = self.active_processes[process_id]
            process_info.process.terminate()

            # Wait a bit for graceful termination
            try:
                await asyncio.wait_for(process_info.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                # Force kill if it doesn't terminate gracefully
                process_info.process.kill()

            del self.active_processes[process_id]
            logger.info("Killed process %s", process_id)
            return True

        except Exception as e:
            logger.error("Error killing process %s: %s", process_id, e)
            return False

    def kill_all_processes(self):
        """Kill all managed processes."""
        for process_id in list(self.active_processes.keys()):
            try:
                process_info = self.active_processes[process_id]
                process_info.process.terminate()
                del self.active_processes[process_id]
            except Exception as e:
                logger.warning("Error killing process %s: %s", process_id, e)

        logger.info("All processes terminated")

    def get_process_info(self, process_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific process.

        Args:
            process_id: Process identifier

        Returns:
            Optional[Dict[str, Any]]: Process information or None
        """
        if process_id not in self.active_processes:
            return None

        info = self.active_processes[process_id]
        return {
            "process_id": info.process_id,
            "command": info.command,
            "pid": info.pid,
            "runtime": info.get_runtime(),
            "user_goal": info.user_goal,
            "start_time": info.start_time,
        }


if __name__ == "__main__":
    """Test the streaming executor functionality."""
    import asyncio
    import sys
    from pathlib import Path

    # Add project root for test imports
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    # Import mock components from test fixtures (Issue #458)
    from tests.fixtures.mocks import MockCommandValidator, MockLLMInterface

    async def test_executor():
        """Test streaming executor with mock components and sample commands."""
        # Create mock components from tests/fixtures/mocks.py
        llm = MockLLMInterface()
        validator = MockCommandValidator()

        # Create executor
        executor = StreamingCommandExecutor(llm, validator)

        logger.info("=== Streaming Executor Test ===")

        # Test commands
        test_commands = [
            ("echo 'Hello, World!'", "test echo command"),
            ("ls -la", "list current directory"),
            (
                f"ping -c 3 {NetworkConstants.PUBLIC_DNS_IP}",
                "test network connectivity",
            ),
            ("sleep 5", "test long-running command"),
        ]

        for command, goal in test_commands:
            logger.info("\nTesting: {command}")
            logger.info("Goal: {goal}")
            logger.info("-" * 50)

            chunk_count = 0
            async for chunk in executor.execute_with_streaming(
                command, goal, timeout=10
            ):
                timestamp = chunk.timestamp.split("T")[1][:8]
                chunk_type = chunk.chunk_type.value.upper()
                content = chunk.content

                logger.info("[%s] %s: %s", timestamp, chunk_type, content)

                chunk_count += 1
                if chunk.chunk_type == ChunkType.COMPLETE:
                    break

                # Limit output for test
                if chunk_count > 20:
                    logger.info("... (limiting output for test)")
                    break

            print()

    asyncio.run(test_executor())
