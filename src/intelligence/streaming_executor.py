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
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.llm_interface import LLMInterface
from src.utils.command_validator import CommandValidator

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

    async def execute_with_streaming(
        self,
        command: str,
        user_goal: str,
        timeout: int = 300,
        provide_commentary: bool = True,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Execute command with real-time streaming output and commentary.

        Args:
            command: Command to execute
            user_goal: Original user goal for context
            timeout: Execution timeout in seconds
            provide_commentary: Whether to provide AI commentary

        Yields:
            StreamChunk: Stream of execution results and commentary
        """
        process_id = str(uuid.uuid4())
        start_time = time.time()

        logger.info(f"Executing command: {command}")
        logger.info(f"Process ID: {process_id}")

        # Validate command safety
        if not self.command_validator.is_command_safe(command):
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.ERROR,
                content=f"❌ Command blocked by security policy: {command}",
                metadata={"security_blocked": True, "command": command},
            )
            return

        # Check process limit
        if len(self.active_processes) >= self._max_processes:
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.ERROR,
                content=(
                    f"❌ Maximum number of concurrent processes "
                    f"({self._max_processes}) reached"
                ),
                metadata={"process_limit_reached": True},
            )
            return

        try:
            # Start process
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.STATUS,
                content=f"🚀 Executing: {command}",
                metadata={"command": command, "process_id": process_id},
            )

            # Parse command safely
            try:
                cmd_parts = shlex.split(command)
            except ValueError as e:
                yield StreamChunk(
                    timestamp=self._get_timestamp(),
                    chunk_type=ChunkType.ERROR,
                    content=f"❌ Invalid command syntax: {str(e)}",
                    metadata={"parse_error": True},
                )
                return

            # Start the process
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
            )

            # Track the process
            process_info = ProcessInfo(
                process_id=process_id,
                command=command,
                pid=process.pid,
                start_time=start_time,
                user_goal=user_goal,
                process=process,
            )
            self.active_processes[process_id] = process_info

            # Stream output with timeout
            try:
                await asyncio.wait_for(
                    self._stream_process_output(
                        process, process_id, user_goal, provide_commentary
                    ),
                    timeout=timeout,
                )

                # Wait for process completion
                return_code = await process.wait()

                # Process completed
                execution_time = time.time() - start_time

                if return_code == 0:
                    yield StreamChunk(
                        timestamp=self._get_timestamp(),
                        chunk_type=ChunkType.COMPLETE,
                        content=(
                            f"✅ Command completed successfully in "
                            f"{execution_time:.2f}s"
                        ),
                        metadata={
                            "success": True,
                            "return_code": return_code,
                            "execution_time": execution_time,
                            "process_id": process_id,
                        },
                    )
                else:
                    yield StreamChunk(
                        timestamp=self._get_timestamp(),
                        chunk_type=ChunkType.COMPLETE,
                        content=(
                            f"⚠️ Command completed with exit code {return_code} "
                            f"in {execution_time:.2f}s"
                        ),
                        metadata={
                            "success": False,
                            "return_code": return_code,
                            "execution_time": execution_time,
                            "process_id": process_id,
                        },
                    )

                # Provide final commentary if enabled
                if provide_commentary and return_code == 0:
                    async for chunk in self._provide_completion_commentary(
                        command, user_goal, execution_time
                    ):
                        yield chunk

            except asyncio.TimeoutError:
                # Process timed out
                yield StreamChunk(
                    timestamp=self._get_timestamp(),
                    chunk_type=ChunkType.ERROR,
                    content=f"⏰ Command timed out after {timeout}s",
                    metadata={"timeout": True, "timeout_duration": timeout},
                )

                # Kill the process
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()

            except Exception as e:
                yield StreamChunk(
                    timestamp=self._get_timestamp(),
                    chunk_type=ChunkType.ERROR,
                    content=f"❌ Execution error: {str(e)}",
                    metadata={"execution_error": True, "error": str(e)},
                )

        except Exception as e:
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.ERROR,
                content=f"❌ Failed to start command: {str(e)}",
                metadata={"startup_error": True, "error": str(e)},
            )

        finally:
            # Clean up process tracking
            if process_id in self.active_processes:
                del self.active_processes[process_id]

    async def _stream_process_output(
        self,
        process: asyncio.subprocess.Process,
        process_id: str,
        user_goal: str,
        provide_commentary: bool,
    ):
        """Stream process output in real-time."""
        stdout_buffer = ""
        stderr_buffer = ""
        commentary_counter = 0

        async def read_stdout():
            nonlocal stdout_buffer, commentary_counter

            while True:
                try:
                    data = await process.stdout.read(1024)
                    if not data:
                        break

                    text = data.decode("utf-8", errors="replace")
                    stdout_buffer += text

                    # Yield stdout chunks
                    lines = text.split("\n")
                    for line in lines:
                        if line.strip():  # Only yield non-empty lines
                            yield StreamChunk(
                                timestamp=self._get_timestamp(),
                                chunk_type=ChunkType.STDOUT,
                                content=line,
                                metadata={"process_id": process_id},
                            )

                    # Provide periodic commentary
                    commentary_counter += len(text)
                    if (
                        provide_commentary and commentary_counter > 500
                    ):  # Every ~500 chars
                        commentary_counter = 0
                        async for chunk in self._provide_progress_commentary(
                            stdout_buffer[-200:], user_goal
                        ):
                            yield chunk

                except Exception as e:
                    logger.warning(f"Error reading stdout: {e}")
                    break

        async def read_stderr():
            nonlocal stderr_buffer

            while True:
                try:
                    data = await process.stderr.read(1024)
                    if not data:
                        break

                    text = data.decode("utf-8", errors="replace")
                    stderr_buffer += text

                    # Yield stderr chunks
                    lines = text.split("\n")
                    for line in lines:
                        if line.strip():  # Only yield non-empty lines
                            yield StreamChunk(
                                timestamp=self._get_timestamp(),
                                chunk_type=ChunkType.STDERR,
                                content=line,
                                metadata={"process_id": process_id},
                            )

                except Exception as e:
                    logger.warning(f"Error reading stderr: {e}")
                    break

        # Collect output from both streams
        tasks = [
            asyncio.create_task(self._collect_chunks(read_stdout())),
            asyncio.create_task(self._collect_chunks(read_stderr())),
        ]

        try:
            while tasks:
                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )

                for task in done:
                    try:
                        chunks = await task
                        for chunk in chunks:
                            yield chunk
                    except Exception as e:
                        logger.warning(f"Error in stream task: {e}")

                    tasks.remove(task)

                tasks = list(pending)

        finally:
            # Cancel remaining tasks
            for task in tasks:
                task.cancel()

    async def _collect_chunks(self, generator) -> List[StreamChunk]:
        """Collect chunks from async generator."""
        chunks = []
        try:
            async for chunk in generator:
                chunks.append(chunk)
                if len(chunks) >= 10:  # Limit batch size
                    break
        except Exception as e:
            logger.warning(f"Error collecting chunks: {e}")
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
                f"Analyze this command output and provide a brief, helpful "
                f"comment about the progress:\n\n"
                f"User Goal: {user_goal}\n"
                f"Recent Output: {recent_output[-150:]}\n\n"
                f"Provide a single, concise comment (max 100 characters) "
                f"about what's happening.\n"
                f"Be helpful and informative, but don't repeat the obvious.\n"
                f"Use emojis when appropriate.\n"
                f"If the output is just routine/boring, respond with "
                f'"SKIP" to avoid spam.'
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
            logger.warning(f"Error generating progress commentary: {e}")

    async def _provide_completion_commentary(
        self, command: str, user_goal: str, execution_time: float
    ) -> AsyncGenerator[StreamChunk, None]:
        """Provide intelligent commentary on command completion."""
        try:
            prompt = (
                f"A command just completed successfully. "
                f"Provide a brief, helpful summary:\n\n"
                f"User Goal: {user_goal}\n"
                f"Command: {command}\n"
                f"Execution Time: {execution_time:.2f}s\n\n"
                f"Provide a single, concise comment (max 150 characters) "
                f"summarizing what was accomplished.\n"
                f"Be helpful and celebrate the success when appropriate.\n"
                f"Use emojis when appropriate."
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
            logger.warning(f"Error generating completion commentary: {e}")

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from src.utils.command_utils import get_timestamp
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
            logger.info(f"Killed process {process_id}")
            return True

        except Exception as e:
            logger.error(f"Error killing process {process_id}: {e}")
            return False

    def kill_all_processes(self):
        """Kill all managed processes."""
        for process_id in list(self.active_processes.keys()):
            try:
                process_info = self.active_processes[process_id]
                process_info.process.terminate()
                del self.active_processes[process_id]
            except Exception as e:
                logger.warning(f"Error killing process {process_id}: {e}")

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

    # Mock components for testing
    class MockLLMInterface:
        async def generate_response(self, prompt, **kwargs):
            # Simple mock responses based on prompt content
            if "progress" in prompt.lower():
                return "Processing data..."
            elif "completion" in prompt.lower():
                return "Task completed successfully!"
            else:
                return "Command executing..."

    class MockCommandValidator:
        def is_command_safe(self, command):
            # Block obviously dangerous commands
            dangerous = ["rm -rf", "format", "del /s"]
            return not any(danger in command.lower() for danger in dangerous)

    async def test_executor():
        # Create mock components
        llm = MockLLMInterface()
        validator = MockCommandValidator()

        # Create executor
        executor = StreamingCommandExecutor(llm, validator)

        print("=== Streaming Executor Test ===")

        # Test commands
        test_commands = [
            ("echo 'Hello, World!'", "test echo command"),
            ("ls -la", "list current directory"),
            ("ping -c 3 8.8.8.8", "test network connectivity"),
            ("sleep 5", "test long-running command"),
        ]

        for command, goal in test_commands:
            print(f"\nTesting: {command}")
            print(f"Goal: {goal}")
            print("-" * 50)

            chunk_count = 0
            async for chunk in executor.execute_with_streaming(
                command, goal, timeout=10
            ):
                timestamp = chunk.timestamp.split("T")[1][:8]
                chunk_type = chunk.chunk_type.value.upper()
                content = chunk.content

                print(f"[{timestamp}] {chunk_type}: {content}")

                chunk_count += 1
                if chunk.chunk_type == ChunkType.COMPLETE:
                    break

                # Limit output for test
                if chunk_count > 20:
                    print("... (limiting output for test)")
                    break

            print()

    asyncio.run(test_executor())
