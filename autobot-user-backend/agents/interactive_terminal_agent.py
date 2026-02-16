# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Interactive Terminal Agent for AutoBot
Handles full terminal emulation with PTY support, sudo handling, and user takeover
"""

import asyncio
import fcntl
import logging
import os
import pty
import select
import struct
import termios
import time
from datetime import datetime
from typing import Any, Dict, Optional

from event_manager import event_manager

from backend.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)


class InteractiveTerminalAgent:
    """Agent that manages interactive terminal sessions with full I/O"""

    def __init__(self, chat_id: str):
        """Initialize interactive terminal agent with PTY session management."""
        self.chat_id = chat_id
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.process: Optional[asyncio.subprocess.Process] = None
        self.session_active = False
        self.input_mode = "agent"  # "agent" or "user"
        self.pending_sudo = False
        self.command_buffer = ""
        self.output_buffer = []
        self._buffer_lock = asyncio.Lock()  # Lock for output_buffer access
        self.start_time = None
        self.terminal_size = (80, 24)  # cols, rows

    def _setup_pty(self) -> None:
        """Create and configure pseudo-terminal for session. Issue #620."""
        self.master_fd, self.slave_fd = pty.openpty()
        self._set_terminal_size(self.terminal_size[0], self.terminal_size[1])
        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def _prepare_env_vars(self, env: Optional[dict]) -> dict:
        """Prepare environment variables for terminal session. Issue #620."""
        env_vars = os.environ.copy()
        if env:
            env_vars.update(env)
        env_vars["TERM"] = "xterm-256color"
        return env_vars

    async def _spawn_process(
        self, command: str, env_vars: dict, cwd: Optional[str]
    ) -> None:
        """Spawn the subprocess attached to PTY. Issue #620."""
        self.process = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-c",
            command,
            stdin=self.slave_fd,
            stdout=self.slave_fd,
            stderr=self.slave_fd,
            env=env_vars,
            cwd=cwd or os.getcwd(),
            preexec_fn=os.setsid,
        )

    async def _notify_session_started(self, command: str) -> None:
        """Publish session started event. Issue #620."""
        await event_manager.publish(
            "terminal_session",
            {
                "chat_id": self.chat_id,
                "status": "started",
                "command": command,
                "pid": self.process.pid,
            },
        )

    async def start_session(
        self, command: str, env: dict = None, cwd: str = None
    ) -> None:
        """Start an interactive terminal session."""
        try:
            self._setup_pty()
            env_vars = self._prepare_env_vars(env)
            await self._spawn_process(command, env_vars, cwd)

            self.session_active = True
            self.start_time = time.time()

            await self._notify_session_started(command)
            asyncio.create_task(self._stream_output())
            logger.info(
                "Started terminal session for chat %s: %s", self.chat_id, command
            )

        except Exception as e:
            logger.error("Failed to start terminal session: %s", e)
            await self._send_error(f"Failed to start terminal: {str(e)}")
            raise

    async def _read_terminal_data(self) -> Optional[bytes]:
        """Read data from terminal (Issue #334 - extracted helper).

        Returns:
            bytes if data available, empty bytes for EOF, None to continue waiting
        """
        if not await self._data_available():
            await asyncio.sleep(TimingConstants.POLL_INTERVAL)
            return None

        try:
            data = os.read(self.master_fd, 4096)
            return data if data else b""  # Empty bytes signals EOF
        except OSError as e:
            if e.errno == 5:  # I/O error - treat as EOF
                return b""
            raise

    async def _stream_output(self):
        """Stream terminal output to chat in real-time"""
        while self.session_active and self.process:
            try:
                # Check if process is still running
                if self.process.returncode is not None:
                    self.session_active = False
                    await self._handle_session_end()
                    break

                data = await self._read_terminal_data()
                if data is None:
                    continue  # No data yet, keep waiting

                if not data:  # EOF reached
                    self.session_active = False
                    await self._handle_session_end()
                    break

                await self._process_output(data)

            except Exception as e:
                logger.error("Error in output streaming: %s", e)
                break

    async def _data_available(self) -> bool:
        """Check if data is available to read"""
        if not self.master_fd:
            return False

        # Use select with timeout to check data availability
        readable, _, _ = select.select([self.master_fd], [], [], 0)
        return bool(readable)

    async def _process_output(self, data: bytes):
        """Process and send terminal output (thread-safe)"""
        try:
            # Decode output
            output = data.decode("utf-8", errors="replace")

            # Add to buffer (thread-safe)
            async with self._buffer_lock:
                self.output_buffer.append(output)

            # Detect special prompts
            if self._detect_sudo_prompt(output):
                self.pending_sudo = True
                await self._handle_sudo_prompt(output)
            elif self._detect_input_prompt(output):
                await self._handle_input_prompt(output)
            else:
                # Regular output
                await self._send_to_chat(output)

        except Exception as e:
            logger.error("Error processing output: %s", e)

    def _detect_sudo_prompt(self, output: str) -> bool:
        """Detect sudo password prompts"""
        sudo_patterns = [
            "[sudo] password",
            "Password:",
            "password for",
            "[sudo] password for",
        ]
        return any(pattern in output for pattern in sudo_patterns)

    def _detect_input_prompt(self, output: str) -> bool:
        """Detect interactive prompts"""
        prompt_patterns = [
            "(y/N)",
            "(Y/n)",
            "[y/N]",
            "[Y/n]",
            "Continue?",
            "Proceed?",
            "Are you sure",
            "Do you want to continue",
        ]
        return any(pattern in output for pattern in prompt_patterns)

    async def _handle_sudo_prompt(self, prompt_data: str):
        """Handle sudo password prompts"""
        await event_manager.publish(
            "terminal_output",
            {
                "chat_id": self.chat_id,
                "output": prompt_data,
                "type": "sudo_prompt",
                "requires_input": True,
                "input_type": "password",
                "message": (
                    "🔐 Sudo password required. "
                    "Click 'Send Input' to provide password."
                ),
            },
        )

        # Switch to user input mode for password
        self.input_mode = "user"

    async def _handle_input_prompt(self, prompt_data: str):
        """Handle interactive prompts"""
        await event_manager.publish(
            "terminal_output",
            {
                "chat_id": self.chat_id,
                "output": prompt_data,
                "type": "input_prompt",
                "requires_input": True,
                "input_type": "text",
                "message": "⌨️ Input required. Enter your response.",
            },
        )

    async def _send_to_chat(self, output: str):
        """Send regular output to chat"""
        await event_manager.publish(
            "terminal_output",
            {
                "chat_id": self.chat_id,
                "output": output,
                "type": "output",
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def _send_error(self, error: str):
        """Send error message to chat"""
        await event_manager.publish(
            "terminal_output",
            {
                "chat_id": self.chat_id,
                "output": f"❌ Error: {error}",
                "type": "error",
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def send_input(self, user_input: str, is_password: bool = False):
        """Send user input to the terminal"""
        if not self.master_fd or not self.session_active:
            await self._send_error("Terminal session is not active")
            return

        try:
            # Add newline if not present
            if not user_input.endswith("\n"):
                user_input += "\n"

            # Write to terminal
            os.write(self.master_fd, user_input.encode())

            # Handle password masking
            if is_password or self.pending_sudo:
                await self._send_to_chat("*** [password sent]\n")
                self.pending_sudo = False
                # Return to agent mode after password
                self.input_mode = "agent"
            else:
                # Echo the command for transparency
                await self._send_to_chat(f"$ {user_input}")

        except Exception as e:
            logger.error("Error sending input: %s", e)
            await self._send_error(f"Failed to send input: {str(e)}")

    async def take_control(self):
        """Allow user to take full control of terminal"""
        self.input_mode = "user"
        await event_manager.publish(
            "terminal_control",
            {
                "chat_id": self.chat_id,
                "status": "user_control",
                "message": (
                    "🎮 You now have control of the terminal. " "Type commands directly."
                ),
            },
        )

    async def return_control(self):
        """Return control to agent"""
        self.input_mode = "agent"
        await event_manager.publish(
            "terminal_control",
            {
                "chat_id": self.chat_id,
                "status": "agent_control",
                "message": "🤖 Agent has resumed control of the terminal.",
            },
        )

    async def resize_terminal(self, cols: int, rows: int):
        """Resize the terminal"""
        if self.master_fd:
            self.terminal_size = (cols, rows)
            self._set_terminal_size(cols, rows)

    def _set_terminal_size(self, cols: int, rows: int):
        """Set terminal size using ioctl"""
        if self.master_fd:
            size = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)

    def _get_signal_map(self) -> Dict[str, int]:
        """Get signal type to signal number mapping (Issue #334 - extracted helper)."""
        return {
            "interrupt": 2,  # SIGINT (Ctrl+C)
            "quit": 3,  # SIGQUIT (Ctrl+\)
            "suspend": 20,  # SIGTSTP (Ctrl+Z)
        }

    async def send_signal(self, signal_type: str):
        """Send signal to the process"""
        if not self.process or not self.session_active:
            return

        try:
            if signal_type == "kill":
                self.process.kill()
            else:
                signal_map = self._get_signal_map()
                signal_num = signal_map.get(signal_type)
                if signal_num:
                    self.process.send_signal(signal_num)

            await self._send_to_chat(f"\n[Signal {signal_type} sent]\n")
        except Exception as e:
            logger.error("Error sending signal: %s", e)

    async def _handle_session_end(self):
        """Handle terminal session end (thread-safe)"""
        duration = time.time() - self.start_time if self.start_time else 0
        exit_code = self.process.returncode if self.process else -1

        # Read buffer length under lock
        async with self._buffer_lock:
            output_lines = len(self.output_buffer)

        await event_manager.publish(
            "terminal_session",
            {
                "chat_id": self.chat_id,
                "status": "ended",
                "exit_code": exit_code,
                "duration": duration,
                "output_lines": output_lines,
            },
        )

        # Cleanup
        await self.cleanup()

    async def wait_for_completion(
        self, timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Wait for the terminal session to complete (thread-safe)"""
        try:
            if self.process:
                await asyncio.wait_for(self.process.wait(), timeout=timeout)

            # Read buffer length under lock
            async with self._buffer_lock:
                line_count = len(self.output_buffer)

            return {
                "exit_code": self.process.returncode if self.process else -1,
                "duration": time.time() - self.start_time if self.start_time else 0,
                "line_count": line_count,
                "status": "completed",
            }
        except asyncio.TimeoutError:
            # Read buffer length under lock
            async with self._buffer_lock:
                line_count = len(self.output_buffer)

            return {
                "exit_code": None,
                "duration": time.time() - self.start_time if self.start_time else 0,
                "line_count": line_count,
                "status": "timeout",
            }

    async def cleanup(self):
        """Clean up terminal session"""
        self.session_active = False

        if self.process:
            try:
                self.process.terminate()
                # Brief delay to allow graceful termination before force kill
                await asyncio.sleep(TimingConstants.MICRO_DELAY)
                if self.process.returncode is None:
                    self.process.kill()
            except Exception as e:
                logger.debug("Process termination during cleanup: %s", e)

        if self.master_fd:
            try:
                os.close(self.master_fd)
            except Exception as e:
                logger.debug("Master fd cleanup (may already be closed): %s", e)

        if self.slave_fd:
            try:
                os.close(self.slave_fd)
            except Exception as e:
                logger.debug("Slave fd cleanup (may already be closed): %s", e)

        self.master_fd = None
        self.slave_fd = None
        self.process = None

        logger.info("Cleaned up terminal session for chat %s", self.chat_id)
