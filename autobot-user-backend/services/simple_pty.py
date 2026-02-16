# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Simple synchronous PTY implementation that works reliably
"""

import logging
import os
import pty
import queue
import select
import signal
import subprocess
import threading
from typing import Optional

from backend.constants.path_constants import PATH
from backend.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for PTY event types
_PTY_OUTPUT_EVENTS = frozenset({"output", "eof"})


def _read_pty_data(fd: int) -> tuple:
    """Read data from PTY and return (event_type, content) (Issue #315: extracted).

    Returns:
        Tuple of (event_type: str, content: str, should_break: bool)
        event_type: 'output', 'eof', or 'error'
        content: The data read or error message
        should_break: True if loop should exit
    """
    try:
        data = os.read(fd, 4096)
        if data:
            output = data.decode("utf-8", errors="replace")
            return ("output", output, False)
        else:
            # EOF
            return ("eof", "", True)
    except OSError as e:
        if e.errno == 5:  # Input/output error - PTY closed
            return ("error", "PTY closed", True)
        logger.error("PTY read error: %s", e)
        return ("error", str(e), False)


class SimplePTY:
    """Simple PTY implementation using synchronous I/O

    Args:
        session_id: Unique identifier for this PTY session
        use_login_shell: If True, starts bash as login shell (--login flag)
                        Login shells load profile files like ~/.bash_profile
        custom_ps1: Optional custom PS1 prompt (e.g., r"\\u@\\h:\\w\\$ ")
    """

    def __init__(
        self,
        session_id: str,
        use_login_shell: bool = False,
        custom_ps1: Optional[str] = None,
    ):
        """Initialize SimplePTY with session ID and optional shell configuration."""
        self.session_id = session_id
        self.use_login_shell = use_login_shell
        self.custom_ps1 = custom_ps1
        self.master_fd = None
        self.process = None
        self.output_queue = queue.Queue()
        self.input_queue = queue.Queue()
        self.running = False
        self.reader_thread = None
        self.writer_thread = None

    @staticmethod
    def configure_terminal_echo(fd: int, enable: bool = True) -> bool:
        """
        Configure terminal echo settings on a PTY file descriptor.

        This is a reusable function that can be called on any PTY fd
        to enable/disable echo and related interactive terminal features.

        Args:
            fd: PTY file descriptor (usually slave fd)
            enable: True to enable echo, False to disable

        Returns:
            True if configuration succeeded, False otherwise

        Technical details:
            - ECHO: Echo input characters to output
            - ECHOE: Visual erase for backspace (erase character)
            - ECHOK: Visual erase for kill (erase line)
            - ECHOCTL: Echo control characters visually (^C, ^D, etc.)
        """
        try:
            import termios

            # Get current terminal settings
            attrs = termios.tcgetattr(fd)

            # Local flags are at index 3
            if enable:
                # Enable echo flags for interactive terminal behavior
                attrs[3] = attrs[3] | termios.ECHO
                attrs[3] = attrs[3] | termios.ECHOE
                attrs[3] = attrs[3] | termios.ECHOK
                attrs[3] = attrs[3] | termios.ECHOCTL
            else:
                # Disable echo flags (useful for password input, silent mode)
                attrs[3] = attrs[3] & ~termios.ECHO
                attrs[3] = attrs[3] & ~termios.ECHOE
                attrs[3] = attrs[3] & ~termios.ECHOK
                attrs[3] = attrs[3] & ~termios.ECHOCTL

            # Apply settings immediately
            termios.tcsetattr(fd, termios.TCSANOW, attrs)

            return True

        except Exception as e:
            logger.warning("Failed to configure terminal echo: %s", e)
            return False

    def start(self, initial_cwd: str = None):
        """Start the PTY"""
        try:
            # Create PTY pair
            self.master_fd, slave_fd = pty.openpty()

            # Configure terminal echo using reusable function
            # This makes the PTY behave like a real interactive terminal
            if self.configure_terminal_echo(slave_fd, enable=True):
                logger.info("Terminal echo enabled for PTY session %s", self.session_id)
            else:
                logger.warning(
                    f"Terminal echo configuration failed for PTY session {self.session_id} (continuing anyway)"
                )

            # Start bash process
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"

            # Set custom PS1 prompt if provided
            if self.custom_ps1:
                env["PS1"] = self.custom_ps1
                logger.info(
                    f"Setting custom PS1 prompt for session {self.session_id}: {self.custom_ps1}"
                )

            # Build bash command with optional --login flag
            bash_cmd = ["/bin/bash"]
            if self.use_login_shell:
                bash_cmd.append("--login")
                logger.info(
                    f"Starting login shell for session {self.session_id} (loads profile files)"
                )

            self.process = subprocess.Popen(
                bash_cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                cwd=initial_cwd or str(PATH.PROJECT_ROOT),
                preexec_fn=os.setsid,
            )

            # Close slave fd in parent
            os.close(slave_fd)

            # Make master fd non-blocking
            os.set_blocking(self.master_fd, False)

            self.running = True

            # Start I/O threads
            self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.writer_thread = threading.Thread(target=self._write_loop, daemon=True)

            self.reader_thread.start()
            self.writer_thread.start()

            logger.info(
                f"PTY started successfully for session {self.session_id}, PID: {self.process.pid}"
            )
            return True

        except Exception as e:
            logger.error("Failed to start PTY: %s", e)
            self.cleanup()
            return False

    def _read_loop(self):
        """Background thread to read from PTY (Issue #315: uses helper)."""
        while self.running and self.master_fd is not None:
            try:
                # Cache master_fd to prevent race condition
                fd = self.master_fd
                if fd is None:
                    break

                # Check for data with select (0.01s = 10ms for responsive input)
                ready, _, _ = select.select([fd], [], [], 0.01)

                if ready:
                    event_type, content, should_break = _read_pty_data(fd)
                    if event_type in _PTY_OUTPUT_EVENTS:
                        self.output_queue.put((event_type, content))
                    if should_break:
                        break

            except Exception as e:
                logger.error("Error in PTY read loop: %s", e)
                break

        self.output_queue.put(("close", ""))
        logger.info("PTY read loop ended for session %s", self.session_id)

    def _write_loop(self):
        """Background thread to write to PTY"""
        while self.running and self.master_fd is not None:
            try:
                # Wait for input without timeout
                try:
                    text = self.input_queue.get_nowait()
                    if text is None:  # Shutdown signal
                        break

                    # Write to PTY
                    data = text.encode("utf-8")

                    # Check master_fd is still valid
                    if self.master_fd is not None:
                        os.write(self.master_fd, data)

                except queue.Empty:
                    continue

            except Exception as e:
                logger.error("Error in PTY write loop: %s", e)
                break

        logger.info("PTY write loop ended for session %s", self.session_id)

    def write_input(self, text: str) -> bool:
        """Write input to PTY"""
        if not self.running:
            return False

        try:
            self.input_queue.put(text)
            return True
        except Exception as e:
            logger.error("Error queuing input: %s", e)
            return False

    def get_output(self) -> Optional[tuple]:
        """Get output from PTY (non-blocking)"""
        try:
            return self.output_queue.get_nowait()
        except queue.Empty:
            return None

    def set_echo(self, enable: bool) -> bool:
        """
        Dynamically change echo setting on running PTY.

        Useful for scenarios where you need to temporarily disable echo
        (e.g., custom password input handling, silent command execution).

        Args:
            enable: True to enable echo, False to disable

        Returns:
            True if successful, False otherwise

        Example:
            pty.set_echo(False)  # Disable echo for password
            pty.write_input("secret_password\\n")
            pty.set_echo(True)   # Re-enable echo
        """
        if not self.running or not self.master_fd:
            logger.warning("Cannot set echo: PTY not running")
            return False

        try:
            # Use the reusable static method on master_fd
            return self.configure_terminal_echo(self.master_fd, enable)
        except Exception as e:
            logger.error("Error setting echo: %s", e)
            return False

    def resize(self, rows: int, cols: int) -> bool:
        """Resize PTY"""
        if not self.running or not self.master_fd:
            return False

        try:
            import fcntl
            import struct
            import termios

            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

            if self.process and self.process.pid:
                os.killpg(os.getpgid(self.process.pid), signal.SIGWINCH)

            return True
        except Exception as e:
            logger.error("Error resizing PTY: %s", e)
            return False

    def send_signal(self, sig: int) -> bool:
        """Send signal to PTY process"""
        if not self.process or not self.process.pid:
            return False

        try:
            os.killpg(os.getpgid(self.process.pid), sig)
            return True
        except Exception as e:
            logger.error("Error sending signal: %s", e)
            return False

    def is_alive(self) -> bool:
        """Check if PTY is alive"""
        return (
            self.running
            and self.process
            and self.process.poll() is None
            and self.master_fd is not None
        )

    def cleanup(self):
        """Clean up PTY"""
        self.running = False

        # Signal writer thread to stop
        try:
            self.input_queue.put(None)
        except Exception as e:
            logger.debug("Failed to signal writer thread: %s", e)

        # Close file descriptor
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except Exception as e:
                logger.debug("Failed to close master fd: %s", e)
            self.master_fd = None

        # Terminate process
        if self.process:
            try:
                self.process.terminate()
                # Give process a moment to terminate gracefully
                import time

                time.sleep(TimingConstants.MICRO_DELAY)
                if self.process.poll() is None:
                    # Process didn't terminate, force kill
                    self.process.kill()
                    # Wait without timeout for kill to complete
                    self.process.wait()
            except Exception as e:
                logger.debug("Failed to terminate process: %s", e)
            self.process = None

        # Wait for threads to complete naturally
        if self.reader_thread and self.reader_thread.is_alive():
            # Signal shutdown via running flag, thread will exit naturally
            pass  # Thread will exit when running=False
        if self.writer_thread and self.writer_thread.is_alive():
            # Thread will exit when running=False and queue is processed
            pass

        logger.info("PTY cleanup completed for session %s", self.session_id)


class SimplePTYManager:
    """Simple PTY manager with thread-safe session management"""

    def __init__(self):
        """Initialize PTY manager with empty sessions dict and thread lock."""
        self.sessions = {}
        self._lock = threading.Lock()  # CRITICAL: Protect concurrent session access

    def create_session(self, session_id: str, initial_cwd: str = None) -> SimplePTY:
        """Create PTY session"""
        # CRITICAL: Atomic check-and-create with lock
        with self._lock:
            if session_id in self.sessions:
                # Close existing session first
                old_pty = self.sessions[session_id]
                old_pty.cleanup()
                del self.sessions[session_id]

            pty = SimplePTY(session_id)
            if pty.start(initial_cwd):
                self.sessions[session_id] = pty
                return pty
            return None

    def get_session(self, session_id: str) -> Optional[SimplePTY]:
        """Get PTY session"""
        with self._lock:
            return self.sessions.get(session_id)

    def close_session(self, session_id: str):
        """Close PTY session"""
        # CRITICAL: Atomic check-and-delete with lock
        with self._lock:
            if session_id in self.sessions:
                pty = self.sessions[session_id]
                del self.sessions[session_id]
            else:
                return
        # Cleanup outside lock to avoid holding lock during I/O
        pty.cleanup()

    def close_all(self):
        """Close all sessions"""
        # CRITICAL: Get list of sessions under lock, then close each
        with self._lock:
            session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            self.close_session(session_id)


# Global instance
simple_pty_manager = SimplePTYManager()
