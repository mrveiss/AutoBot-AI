# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Simple synchronous PTY implementation that works reliably
"""

import collections
import os
import pty
import queue
import signal
import subprocess
import threading
import time

from autobot_shared.fd_poll import poll_readable, seconds_to_poll_timeout_ms
from autobot_shared.logging_manager import get_logger
from constants.path_constants import PATH
from constants.threshold_constants import TimingConstants

logger = get_logger(__name__)

# Issue #380: Module-level frozenset for PTY event types
_PTY_OUTPUT_EVENTS = frozenset({"output", "eof"})

#: Characters of recent output a PTY keeps for readers that must not consume its
#: output queue -- the queue belongs to the terminal WebSocket (#17074). The
#: oldest output is dropped past this, whole chunks at a time.
_TRANSCRIPT_MAX_CHARS = 1_000_000

# Issue #13219: same 10 ms wait the read loop always used, expressed in the
# milliseconds poll() takes instead of the seconds select() took.
_READ_POLL_TIMEOUT_MS = seconds_to_poll_timeout_ms(TimingConstants.POLL_INTERVAL)

#: How long the write loop waits for input before re-checking its own stop
#: conditions (#17355). NOT a latency budget: `get()` returns the moment an item
#: is queued, so this bounds only how often an IDLE loop wakes, and how long
#: after `running = False` the thread notices. `get_nowait()` made both zero --
#: the loop re-entered immediately and every idle session burned a core.
_WRITE_WAIT_TIMEOUT_S = TimingConstants.MICRO_DELAY

#: How long to wait before retrying a write the PTY buffer had no room for
#: (#17381). `master_fd` is non-blocking (`os.set_blocking(..., False)` in
#: `_spawn`), so `os.write` raises `BlockingIOError` when the buffer is full.
#: That means "not now", not "failed".
_WRITE_RETRY_WAIT_S = TimingConstants.MICRO_DELAY

#: How long `_write_all` tolerates making NO progress before giving up (#17381).
#: Deliberately a stall budget rather than a total one: a 1 MiB paste needs many
#: buffer-fills, so a cap on total elapsed time would truncate the large writes
#: this method exists to deliver. The clock resets on every byte accepted.
_WRITE_STALL_BUDGET_S = TimingConstants.MEDIUM_DELAY

#: Grace period for the child to exit after SIGTERM before SIGKILL.
#: A SEPARATE name from `_WRITE_WAIT_TIMEOUT_S` even though both currently
#: resolve to the same SSOT value: they are unrelated timings, and one constant
#: serving two purposes means tuning either one silently moves the other.
_PROC_TERM_GRACE_S = TimingConstants.MICRO_DELAY


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
        return ("error", "PTY read error", False)


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
        custom_ps1: str | None = None,
    ) -> None:
        """Initialize SimplePTY with session ID and optional shell configuration."""
        self.session_id = session_id
        self.use_login_shell = use_login_shell
        self.custom_ps1 = custom_ps1
        self.master_fd = None
        self.process = None
        self.output_queue = queue.Queue()
        self.input_queue = queue.Queue()
        # #17074: a bounded copy of the output, addressed by absolute offset.
        self._transcript: collections.deque[str] = collections.deque()
        self._transcript_len = 0  # characters currently held
        self._transcript_base = 0  # absolute offset of the first held character
        self._transcript_lock = threading.Lock()
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

    def _spawn_bash_process(self, slave_fd, env: dict, initial_cwd: str) -> None:
        """Helper for start. Ref: #1088. Spawns the bash subprocess and sets fd state."""
        bash_cmd = ["/bin/bash"]
        if self.use_login_shell:
            bash_cmd.append("--login")
            logger.info(f"Starting login shell for session {self.session_id} (loads profile files)")
        self.process = (
            subprocess.Popen(  # nosec B603  # bash_cmd is ["/bin/bash"] with optional --login; fixed absolute path
                bash_cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                cwd=initial_cwd or str(PATH.PROJECT_ROOT),
                preexec_fn=os.setsid,
            )
        )
        os.close(slave_fd)
        os.set_blocking(self.master_fd, False)
        self.running = True

    def start(self, initial_cwd: str = None):
        """Start the PTY. Ref: #1088."""
        try:
            self.master_fd, slave_fd = pty.openpty()

            # Configure terminal echo
            if self.configure_terminal_echo(slave_fd, enable=True):
                logger.info("Terminal echo enabled for PTY session %s", self.session_id)
            else:
                logger.warning(
                    f"Terminal echo configuration failed for PTY session {self.session_id} (continuing anyway)"
                )

            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            if self.custom_ps1:
                env["PS1"] = self.custom_ps1
                logger.info(f"Setting custom PS1 prompt for session {self.session_id}: {self.custom_ps1}")

            self._spawn_bash_process(slave_fd, env, initial_cwd)

            self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.writer_thread = threading.Thread(target=self._write_loop, daemon=True)
            self.reader_thread.start()
            self.writer_thread.start()

            logger.info(f"PTY started successfully for session {self.session_id}, PID: {self.process.pid}")
            return True

        except Exception as e:
            logger.error("Failed to start PTY: %s", e)
            self.cleanup()
            return False

    def _read_loop(self) -> None:
        """Background thread to read from PTY (Issue #315: uses helper)."""
        while self.running and self.master_fd is not None:
            try:
                # Cache master_fd to prevent race condition
                fd = self.master_fd
                if fd is None:
                    break

                # Check for data with poll (10ms for responsive input). poll()
                # has no FD_SETSIZE ceiling, so a PTY fd >= 1024 still works
                # where select() raised "filedescriptor out of range" (#13219).
                if poll_readable(fd, _READ_POLL_TIMEOUT_MS):
                    event_type, content, should_break = _read_pty_data(fd)
                    if event_type in _PTY_OUTPUT_EVENTS:
                        self.output_queue.put((event_type, content))
                    if event_type == "output" and content:
                        self._append_transcript(content)
                    if should_break:
                        break

            except Exception as e:
                logger.error("Error in PTY read loop: %s", e)
                break

        self.output_queue.put(("close", ""))
        logger.info("PTY read loop ended for session %s", self.session_id)

    def _write_all(self, data: bytes) -> None:
        """Write every byte of *data* to the PTY, honouring backpressure.

        `master_fd` is NON-BLOCKING, so one `os.write` expresses two outcomes a
        single call cannot: it may write FEWER bytes than handed to it, and it
        may raise `BlockingIOError` meaning the buffer is full right now.

        Neither is an error, and treating them as one loses user input silently
        (#17381):

        * discarding the short-write remainder truncates a large paste, at a
          byte boundary that can split a multi-byte UTF-8 character;
        * letting `BlockingIOError` reach the caller's broad `except` ends the
          write thread for the life of the session. The read loop keeps
          streaming output, so the terminal looks healthy while accepting no
          input at all.

        The bound is time SINCE LAST PROGRESS, not total elapsed. A total
        budget looks equivalent and is not: a large paste to a slow reader takes
        many buffer-fills to deliver, so a total bound truncates exactly the
        write it was supposed to protect -- reintroducing this bug for big
        inputs while passing every small-input test. The test with a 1 MiB
        payload is what caught that; the first version of this method had it.

        On exhaustion the `BlockingIOError` is re-raised deliberately: a child
        that has not accepted a single byte in that long is wedged, and failing
        loudly beats retrying forever.
        """
        view = memoryview(data)
        deadline = time.monotonic() + _WRITE_STALL_BUDGET_S
        while view:
            fd = self.master_fd
            if fd is None:
                # cleanup() ran mid-write. Not an error worth raising past the
                # loop's own stop conditions, which already say to finish.
                logger.debug("PTY descriptor closed mid-write for session %s", self.session_id)
                return
            try:
                written = os.write(fd, view)
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(_WRITE_RETRY_WAIT_S)
                continue
            if written:
                # Progress resets the stall clock: the budget exists to detect a
                # child that has stopped reading, not to cap how long a large
                # write legitimately takes.
                deadline = time.monotonic() + _WRITE_STALL_BUDGET_S
            view = view[written:]

    def _write_loop(self) -> None:
        """Write queued input to the PTY, waiting between items (#17355).

        The wait is BOUNDED, not blocking, and not absent. `get_nowait()` made
        this a hot spin: `queue.Empty` on an idle session re-entered the loop
        immediately, so one saturated core per live terminal, whether or not
        anything ever leaked.

        A plain blocking `get()` is the trap, because it looks correct against
        `cleanup()`, which does send a `None` sentinel. It would park forever on
        three paths that stop this loop without one: the sentinel's `put` sits
        inside a swallowing `try/except` AFTER `running = False` is already set,
        an abandoned session never calls `cleanup()` at all, and the loop's
        second condition -- `master_fd is not None` -- is signalled by nothing.
        The timeout is what lets both conditions be re-checked regardless of
        what the caller did, failed to do, or documented.
        """
        while self.running and self.master_fd is not None:
            try:
                # Bounded wait: returns immediately when input arrives, and
                # otherwise hands control back to the conditions above.
                try:
                    text = self.input_queue.get(timeout=_WRITE_WAIT_TIMEOUT_S)
                    if text is None:  # Shutdown signal
                        break

                    # _write_all, not os.write: the descriptor is non-blocking,
                    # so a bare call can short-write or raise EAGAIN and both
                    # lose input silently (#17381).
                    self._write_all(text.encode("utf-8"))

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

    def _append_transcript(self, text: str) -> None:
        """Keep a copy of *text* for transcript readers, dropping the oldest past the cap."""
        with self._transcript_lock:
            self._transcript.append(text)
            self._transcript_len += len(text)
            while self._transcript_len > _TRANSCRIPT_MAX_CHARS and len(self._transcript) > 1:
                dropped = self._transcript.popleft()
                self._transcript_len -= len(dropped)
                self._transcript_base += len(dropped)

    def transcript_position(self) -> int:
        """Absolute offset just past the last output received (#17074)."""
        with self._transcript_lock:
            return self._transcript_base + self._transcript_len

    def read_transcript(self, since: int) -> tuple[int, str]:
        """Output received after absolute offset *since*, without consuming the output queue (#17074).

        Returns ``(offset, text)``: the absolute offset *text* starts at, read
        atomically with it. An offset past *since* means the output in between
        was already dropped under the cap -- the caller has lost it, and knows.
        """
        with self._transcript_lock:
            parts, offset = [], self._transcript_base
            for chunk in self._transcript:
                end = offset + len(chunk)
                if end > since:
                    parts.append(chunk[max(since - offset, 0) :])
                offset = end
            return max(since, self._transcript_base), "".join(parts)

    def get_output(self) -> tuple | None:
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
        return self.running and self.process and self.process.poll() is None and self.master_fd is not None

    def cleanup(self) -> None:
        """Clean up PTY"""
        self.running = False

        # Signal writer thread to stop
        try:
            self.input_queue.put(None)
        except Exception as e:
            logger.debug("Failed to signal writer thread: %s", e)

        # Close file descriptor
        if self.master_fd:
            # Publish None FIRST, then close the fd we took (#17381). The old
            # order closed it and set None afterwards, leaving a window where
            # the write loop could read a descriptor that was already closed --
            # and, after the number was reused, one belonging to something else.
            fd, self.master_fd = self.master_fd, None
            try:
                os.close(fd)
            except Exception as e:
                logger.debug("Failed to close master fd: %s", e)

        # Terminate process
        if self.process:
            try:
                self.process.terminate()
                # Wait briefly for graceful shutdown; avoids blocking sleep on event loop
                try:
                    self.process.wait(timeout=_PROC_TERM_GRACE_S)
                except Exception:
                    # Process didn't terminate within timeout — force kill
                    self.process.kill()
                    # Wait without timeout for kill to complete
                    self.process.wait()
            except Exception as e:
                logger.debug("Failed to terminate process: %s", e)
            self.process = None

        # #17355: this does NOT wait, and the comments here used to say it did.
        # Both threads exit on their own next iteration -- the reader within
        # _READ_POLL_TIMEOUT_MS, the writer within _WRITE_WAIT_TIMEOUT_S -- so
        # the exit is bounded, but nothing here joins them and cleanup() returns
        # before either has finished. That was true only because the writer
        # spun; now it is true because both waits are bounded. No join is added
        # deliberately: cleanup() is reached from async request paths, and a
        # blocking join there would stall an event loop to save a few
        # milliseconds of thread lifetime.

        logger.info("PTY cleanup completed for session %s", self.session_id)


class SimplePTYManager:
    """Simple PTY manager with thread-safe session management"""

    def __init__(self) -> None:
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

    def get_session(self, session_id: str) -> SimplePTY | None:
        """Get PTY session"""
        with self._lock:
            return self.sessions.get(session_id)

    def close_session(self, session_id: str) -> None:
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

    def close_all(self) -> None:
        """Close all sessions"""
        # CRITICAL: Get list of sessions under lock, then close each
        with self._lock:
            session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            self.close_session(session_id)


# Global instance
simple_pty_manager = SimplePTYManager()
