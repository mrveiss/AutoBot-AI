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
from typing import Callable, Optional

from src.constants.network_constants import NetworkConstants
from src.constants.path_constants import PATH

logger = logging.getLogger(__name__)


class SimplePTY:
    """Simple PTY implementation using synchronous I/O"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.master_fd = None
        self.process = None
        self.output_queue = queue.Queue()
        self.input_queue = queue.Queue()
        self.running = False
        self.reader_thread = None
        self.writer_thread = None

    def start(self, initial_cwd: str = None):
        """Start the PTY"""
        try:
            # Create PTY pair
            self.master_fd, slave_fd = pty.openpty()

            # Start bash process
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"

            self.process = subprocess.Popen(
                ["/bin/bash"],
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
            logger.error(f"Failed to start PTY: {e}")
            self.cleanup()
            return False

    def _read_loop(self):
        """Background thread to read from PTY"""
        while self.running and self.master_fd is not None:
            try:
                # Cache master_fd to prevent race condition
                fd = self.master_fd
                if fd is None:
                    break

                # Check for data with select
                ready, _, _ = select.select([fd], [], [], 0.1)

                if ready:
                    try:
                        data = os.read(fd, 4096)
                        if data:
                            output = data.decode("utf-8", errors="replace")
                            self.output_queue.put(("output", output))
                        else:
                            # EOF
                            self.output_queue.put(("eof", ""))
                            break
                    except OSError as e:
                        if e.errno == 5:  # Input/output error - PTY closed
                            break
                        logger.error(f"PTY read error: {e}")

            except Exception as e:
                logger.error(f"Error in PTY read loop: {e}")
                break

        self.output_queue.put(("close", ""))
        logger.info(f"PTY read loop ended for session {self.session_id}")

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
                logger.error(f"Error in PTY write loop: {e}")
                break

        logger.info(f"PTY write loop ended for session {self.session_id}")

    def write_input(self, text: str) -> bool:
        """Write input to PTY"""
        if not self.running:
            return False

        try:
            self.input_queue.put(text)
            return True
        except Exception as e:
            logger.error(f"Error queuing input: {e}")
            return False

    def get_output(self) -> Optional[tuple]:
        """Get output from PTY (non-blocking)"""
        try:
            return self.output_queue.get_nowait()
        except queue.Empty:
            return None

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
            logger.error(f"Error resizing PTY: {e}")
            return False

    def send_signal(self, sig: int) -> bool:
        """Send signal to PTY process"""
        if not self.process or not self.process.pid:
            return False

        try:
            os.killpg(os.getpgid(self.process.pid), sig)
            return True
        except Exception as e:
            logger.error(f"Error sending signal: {e}")
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
        except:
            pass

        # Close file descriptor
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except:
                pass
            self.master_fd = None

        # Terminate process
        if self.process:
            try:
                self.process.terminate()
                # Give process a moment to terminate gracefully
                import time

                time.sleep(0.1)
                if self.process.poll() is None:
                    # Process didn't terminate, force kill
                    self.process.kill()
                    # Wait without timeout for kill to complete
                    self.process.wait()
            except:
                pass
            self.process = None

        # Wait for threads to complete naturally
        if self.reader_thread and self.reader_thread.is_alive():
            # Signal shutdown via running flag, thread will exit naturally
            pass  # Thread will exit when running=False
        if self.writer_thread and self.writer_thread.is_alive():
            # Thread will exit when running=False and queue is processed
            pass

        logger.info(f"PTY cleanup completed for session {self.session_id}")


class SimplePTYManager:
    """Simple PTY manager"""

    def __init__(self):
        self.sessions = {}

    def create_session(self, session_id: str, initial_cwd: str = None) -> SimplePTY:
        """Create PTY session"""
        if session_id in self.sessions:
            self.close_session(session_id)

        pty = SimplePTY(session_id)
        if pty.start(initial_cwd):
            self.sessions[session_id] = pty
            return pty
        return None

    def get_session(self, session_id: str) -> Optional[SimplePTY]:
        """Get PTY session"""
        return self.sessions.get(session_id)

    def close_session(self, session_id: str):
        """Close PTY session"""
        if session_id in self.sessions:
            pty = self.sessions[session_id]
            pty.cleanup()
            del self.sessions[session_id]

    def close_all(self):
        """Close all sessions"""
        for session_id in list(self.sessions.keys()):
            self.close_session(session_id)


# Global instance
simple_pty_manager = SimplePTYManager()
