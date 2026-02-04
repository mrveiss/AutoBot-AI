# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Command Utilities - Centralized Command Execution
==================================================

Provides consistent command execution patterns for all agents.
Eliminates duplicate subprocess handling code across the codebase.

Issue #751: Consolidate Common Utilities

Usage:
    from src.utils.command_utils import execute_command, execute_shell_command

    # Simple exec-style (for specific commands like 'man')
    result = await execute_command(["man", "-w", "ls"], timeout=5.0)

    # Shell command (for complex shell expressions)
    result = await execute_shell_command("ls -la | grep .py")

    # Streaming output
    async for chunk in execute_shell_command_streaming("long_running_cmd"):
        logger.info(chunk.content)  # Process each chunk
"""
import asyncio
import logging
from asyncio import Queue as AsyncQueue
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

# Issue #765: Use centralized strip_ansi_codes from encoding_utils
from src.utils.encoding_utils import strip_ansi_codes

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "strip_ansi_codes",
    "get_timestamp",
    "execute_shell_command",
    "execute_command",
    "execute_shell_command_streaming",
    "CommandResult",
    "StreamChunk",
]


@dataclass
class CommandResult:
    """Result of a command execution."""

    stdout: str
    stderr: str
    return_code: int
    status: str  # "success", "error", "timeout"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "status": self.status,
        }


@dataclass
class StreamChunk:
    """A chunk of streaming command output."""

    content: str
    chunk_type: str  # "stdout", "stderr"
    is_final: bool = False


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()


async def execute_shell_command(command: str) -> Dict[str, Any]:
    """
    Executes a shell command asynchronously and cleans the output.

    Args:
        command: The shell command to execute.

    Returns:
        A dictionary containing cleaned stdout, stderr, return code, and status.
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        # Issue #765: Use explicit UTF-8 encoding with error handling
        stdout_str = strip_ansi_codes(stdout.decode("utf-8", errors="replace")).strip()
        stderr_str = strip_ansi_codes(stderr.decode("utf-8", errors="replace")).strip()
        return_code = process.returncode

        status = "success" if return_code == 0 else "error"

        return {
            "stdout": stdout_str,
            "stderr": stderr_str,
            "return_code": return_code,
            "status": status,
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": f"Command not found: {command}",
            "return_code": 127,  # Common return code for command not found
            "status": "error",
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Error executing command: {e}",
            "return_code": 1,  # Generic error code
            "status": "error",
        }


def _prepare_process_env(env: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """
    Prepare environment variables for subprocess execution.

    Merges provided environment variables with the current environment.
    Issue #620.

    Args:
        env: Optional environment variables to merge

    Returns:
        Merged environment dict or None if no custom env provided
    """
    import os

    if env:
        process_env = os.environ.copy()
        process_env.update(env)
        return process_env
    return None


def _parse_command_output(
    stdout: bytes, stderr: bytes, return_code: int
) -> CommandResult:
    """
    Parse and clean command output into a CommandResult.

    Decodes bytes to strings, strips ANSI codes, and determines status.
    Issue #620.

    Args:
        stdout: Raw stdout bytes
        stderr: Raw stderr bytes
        return_code: Process return code

    Returns:
        CommandResult with cleaned output
    """
    stdout_str = strip_ansi_codes(stdout.decode("utf-8", errors="replace")).strip()
    stderr_str = strip_ansi_codes(stderr.decode("utf-8", errors="replace")).strip()
    status = "success" if return_code == 0 else "error"

    return CommandResult(
        stdout=stdout_str,
        stderr=stderr_str,
        return_code=return_code,
        status=status,
    )


def _create_timeout_result(args: List[str], timeout: float) -> CommandResult:
    """
    Create a CommandResult for a timed-out command.

    Issue #620.

    Args:
        args: Command arguments that were executed
        timeout: Timeout value in seconds

    Returns:
        CommandResult with timeout status
    """
    return CommandResult(
        stdout="",
        stderr=f"Command timed out after {timeout}s: {' '.join(args)}",
        return_code=-1,
        status="timeout",
    )


def _create_not_found_result(args: List[str]) -> CommandResult:
    """
    Create a CommandResult for a command not found error.

    Issue #620.

    Args:
        args: Command arguments (first element is the command name)

    Returns:
        CommandResult with error status
    """
    cmd_str = args[0] if args else "unknown"
    return CommandResult(
        stdout="",
        stderr=f"Command not found: {cmd_str}",
        return_code=127,
        status="error",
    )


def _create_execution_error_result(args: List[str], error: Exception) -> CommandResult:
    """
    Create a CommandResult for a general execution error.

    Issue #620.

    Args:
        args: Command arguments that were executed
        error: The exception that occurred

    Returns:
        CommandResult with error status
    """
    logger.error("Error executing command %s: %s", args, error)
    return CommandResult(
        stdout="",
        stderr=f"Error executing command: {error}",
        return_code=1,
        status="error",
    )


async def execute_command(
    args: List[str],
    timeout: Optional[float] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> CommandResult:
    """
    Execute a command with arguments (exec-style, not shell).

    Safer than shell execution as it doesn't invoke a shell interpreter.
    Use this for specific commands with known arguments.

    Args:
        args: Command and arguments as a list (e.g., ["man", "-w", "ls"])
        timeout: Optional timeout in seconds
        cwd: Optional working directory
        env: Optional environment variables (merged with current env)

    Returns:
        CommandResult with stdout, stderr, return_code, and status

    Example:
        result = await execute_command(["man", "-w", "ls"], timeout=5.0)
        if result.status == "success":
            logger.info("Output: %s", result.stdout)
    """
    try:
        process_env = _prepare_process_env(env)
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=process_env,
        )

        try:
            if timeout:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            else:
                stdout, stderr = await process.communicate()
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return _create_timeout_result(args, timeout)

        return _parse_command_output(stdout, stderr, process.returncode)

    except FileNotFoundError:
        return _create_not_found_result(args)
    except Exception as e:
        return _create_execution_error_result(args, e)


def _create_stream_reader(
    output_queue: AsyncQueue,
    on_output: Optional[Callable[[StreamChunk], None]],
) -> Callable:
    """
    Create a coroutine factory for reading process streams.

    Returns a coroutine that reads lines from a stream and queues them
    as StreamChunk objects. Issue #620.

    Args:
        output_queue: Queue to put chunks into
        on_output: Optional callback for each chunk

    Returns:
        Coroutine factory for reading streams
    """

    async def read_stream(stream, chunk_type: str):
        """Read from stream and queue chunks."""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                content = line.decode("utf-8", errors="replace")
                chunk = StreamChunk(
                    content=content,
                    chunk_type=chunk_type,
                    is_final=False,
                )
                await output_queue.put(chunk)
                if on_output:
                    on_output(chunk)
        except Exception as e:
            logger.error("Error reading %s: %s", chunk_type, e)

    return read_stream


async def _yield_chunks_from_queue(
    output_queue: AsyncQueue,
    done_event: asyncio.Event,
) -> AsyncGenerator[StreamChunk, None]:
    """
    Yield chunks from the output queue until processing is complete.

    Polls the queue with a timeout to allow checking if stream processing
    is complete. Issue #620.

    Args:
        output_queue: Queue containing StreamChunk objects
        done_event: Event signaling when stream processing is complete

    Yields:
        StreamChunk objects as they arrive in the queue
    """
    while not done_event.is_set() or not output_queue.empty():
        try:
            chunk = await asyncio.wait_for(output_queue.get(), timeout=0.1)
            yield chunk
        except asyncio.TimeoutError:
            continue


def _create_final_chunk(
    return_code: int,
    on_output: Optional[Callable[[StreamChunk], None]],
) -> StreamChunk:
    """
    Create the final status chunk after process completion.

    Issue #620.

    Args:
        return_code: Process exit code
        on_output: Optional callback for the chunk

    Returns:
        StreamChunk with process exit status
    """
    final_chunk = StreamChunk(
        content=f"[Process exited with code {return_code}]",
        chunk_type="status",
        is_final=True,
    )
    if on_output:
        on_output(final_chunk)
    return final_chunk


def _create_error_chunk(
    error: Exception,
    on_output: Optional[Callable[[StreamChunk], None]],
) -> StreamChunk:
    """
    Create an error chunk for streaming command failures.

    Issue #620.

    Args:
        error: The exception that occurred
        on_output: Optional callback for the chunk

    Returns:
        StreamChunk with error information
    """
    error_chunk = StreamChunk(
        content=f"Error: {error}",
        chunk_type="error",
        is_final=True,
    )
    if on_output:
        on_output(error_chunk)
    return error_chunk


async def execute_shell_command_streaming(
    command: str,
    on_output: Optional[Callable[[StreamChunk], None]] = None,
) -> AsyncGenerator[StreamChunk, None]:
    """
    Execute a shell command with streaming output.

    Yields output chunks as they become available, useful for long-running
    commands where real-time output is needed.

    Args:
        command: Shell command to execute
        on_output: Optional callback for each output chunk

    Yields:
        StreamChunk objects with content and type (stdout/stderr)

    Example:
        async for chunk in execute_shell_command_streaming("apt update"):
            logger.debug("[%s] %s", chunk.chunk_type, chunk.content)
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        output_queue: AsyncQueue[StreamChunk] = AsyncQueue()
        done_event = asyncio.Event()
        read_stream = _create_stream_reader(output_queue, on_output)

        # Start reading both streams concurrently
        stdout_task = asyncio.create_task(read_stream(process.stdout, "stdout"))
        stderr_task = asyncio.create_task(read_stream(process.stderr, "stderr"))

        async def wait_for_completion():
            """Wait for both streams to complete."""
            await asyncio.gather(stdout_task, stderr_task)
            done_event.set()

        completion_task = asyncio.create_task(wait_for_completion())

        # Yield chunks as they arrive
        async for chunk in _yield_chunks_from_queue(output_queue, done_event):
            yield chunk

        await process.wait()
        await completion_task
        yield _create_final_chunk(process.returncode, on_output)

    except Exception as e:
        logger.error("Error in streaming command execution: %s", e)
        yield _create_error_chunk(e, on_output)
