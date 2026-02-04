# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal WebSocket State Manager
Provides thread-safe and race-condition-free terminal WebSocket management
"""

import asyncio
import logging
import os
import pty
import queue
import subprocess  # nosec B404 - required for PTY shell process management
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

from src.constants.path_constants import PATH

logger = logging.getLogger(__name__)


def _terminate_process_with_fallback(process: subprocess.Popen) -> None:
    """Terminate process gracefully with kill fallback (Issue #315 - extracted)."""
    if not process:
        return
    try:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
    except Exception as e:
        logger.warning("Error terminating process: %s", e)


def _decode_and_process_output(
    data: bytes, output_processor: Optional[Callable[[str], str]]
) -> str:
    """Decode PTY output and apply optional processing (Issue #315 - extracted)."""
    output = data.decode("utf-8", errors="replace")
    if output_processor:
        output = output_processor(output)
    return output


def _increment_stat_sync(stats_lock, stats: Dict[str, int], key: str) -> None:
    """Increment a stat counter with thread-safe locking (Issue #315)."""
    with stats_lock:
        stats[key] += 1


class TerminalState(Enum):
    """Terminal session states"""

    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class TerminalWebSocketManager:
    """
    Thread-safe terminal WebSocket manager with proper state synchronization.
    Fixes race conditions in PTY management and WebSocket communication.
    """

    def __init__(self, terminal_type: str = "bash"):
        """Initialize the terminal WebSocket manager."""
        self.terminal_type = terminal_type

        # State management with lock
        self._state = TerminalState.STOPPED
        self._state_lock = asyncio.Lock()

        # Lock for thread-safe stats access
        self._stats_lock = threading.Lock()

        # WebSocket and PTY resources
        self.websocket = None
        self.pty_fd: Optional[int] = None
        self.process: Optional[subprocess.Popen] = None

        # Threading resources
        self.reader_thread: Optional[threading.Thread] = None
        self.output_queue: queue.Queue = queue.Queue(maxsize=1000)
        self.output_sender_task: Optional[asyncio.Task] = None

        # Configuration
        self.current_dir = str(PATH.USER_HOME)
        self.env = os.environ.copy()

        # Message processing hooks
        self.input_processor: Optional[Callable[[str], str]] = None
        self.output_processor: Optional[Callable[[str], str]] = None
        self.message_sender: Optional[Callable[[Dict[str, Any]], None]] = None

        # Statistics
        self.stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "errors": 0,
            "start_time": None,
        }

    async def get_state(self) -> TerminalState:
        """Get current terminal state thread-safely."""
        async with self._state_lock:
            return self._state

    async def _set_state(self, new_state: TerminalState):
        """Set terminal state thread-safely."""
        async with self._state_lock:
            old_state = self._state
            self._state = new_state
            logger.debug(
                f"Terminal state changed: {old_state.value} -> {new_state.value}"
            )

    def set_message_sender(self, sender: Callable[[Dict[str, Any]], None]):
        """Set the function to send messages to WebSocket client."""
        self.message_sender = sender

    def set_input_processor(self, processor: Callable[[str], str]):
        """Set custom input processing function."""
        self.input_processor = processor

    def set_output_processor(self, processor: Callable[[str], str]):
        """Set custom output processing function."""
        self.output_processor = processor

    async def start_session(self, websocket):
        """Start a new terminal session with proper state management."""
        state = await self.get_state()

        if state != TerminalState.STOPPED:
            raise RuntimeError(f"Cannot start session in state: {state.value}")

        await self._set_state(TerminalState.INITIALIZING)

        try:
            self.websocket = websocket
            with self._stats_lock:
                self.stats["start_time"] = time.time()

            # Create PTY with proper error handling
            await self._create_pty()

            # Start background tasks
            await self._start_background_tasks()

            await self._set_state(TerminalState.RUNNING)
            logger.info("Terminal session started successfully: %s", self.terminal_type)

        except Exception as e:
            await self._set_state(TerminalState.ERROR)
            logger.error("Failed to start terminal session: %s", e)
            await self._cleanup_resources()
            raise

    async def _create_pty(self):
        """Create PTY and start shell process."""
        try:
            # Run blocking PTY creation in thread pool to avoid blocking event loop
            # Issue #291: Convert blocking I/O to async
            master_fd, _, process = await asyncio.to_thread(self._sync_create_pty)
            self.pty_fd = master_fd
            self.process = process

            logger.debug("PTY created: fd=%s, pid=%s", master_fd, self.process.pid)

        except Exception as e:
            logger.error("Failed to create PTY: %s", e)
            raise

    def _configure_pty_attrs(self, slave_fd: int) -> None:
        """Configure PTY terminal attributes for shell operation. Issue #620."""
        import termios

        attrs = termios.tcgetattr(slave_fd)
        # Disable auto CR/LF and XON/XOFF
        attrs[0] &= ~(termios.ICRNL | termios.IXON)
        attrs[3] &= ~termios.ECHO  # Disable echo
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)

    def _cleanup_pty_fds(
        self, master_fd: Optional[int], slave_fd: Optional[int]
    ) -> None:
        """Clean up PTY file descriptors on error. Issue #620."""
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError as close_err:
                logger.debug("Master fd close error: %s", close_err)
        if slave_fd is not None:
            try:
                os.close(slave_fd)
            except OSError as close_err:
                logger.debug("Slave fd close error: %s", close_err)

    def _sync_create_pty(self):
        """Synchronous PTY creation - runs in thread pool.

        This is separated from _create_pty to run blocking operations
        (pty.openpty, termios, subprocess.Popen) in a thread pool.
        """
        master_fd, slave_fd = pty.openpty()

        try:
            self._configure_pty_attrs(slave_fd)

            def safe_preexec():
                """Safe preexec function that handles errors gracefully"""
                try:
                    os.setsid()
                except OSError as e:
                    logger.warning("setsid failed in preexec_fn: %s", e)

            process = subprocess.Popen(
                ["/bin/bash", "-i"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.current_dir,
                env=self.env,
                preexec_fn=safe_preexec,
                start_new_session=True,
            )

            os.close(slave_fd)
            slave_fd = None  # Mark as closed for cleanup

            if process.poll() is not None:
                raise RuntimeError("Shell process failed to start")

            return master_fd, None, process

        except Exception as e:
            self._cleanup_pty_fds(master_fd, slave_fd)
            raise RuntimeError(f"PTY creation failed: {e}")

    async def _start_background_tasks(self):
        """Start background reader thread and output sender task."""
        # Start PTY reader thread
        self.reader_thread = threading.Thread(
            target=self._pty_reader_thread,
            daemon=True,
            name=f"PTYReader-{self.terminal_type}",
        )
        self.reader_thread.start()

        # Start async output sender task
        self.output_sender_task = asyncio.create_task(
            self._output_sender_loop(), name=f"OutputSender-{self.terminal_type}"
        )

    def _pty_reader_thread(self):
        """Background thread to read PTY output with proper error handling."""
        import select

        logger.debug("PTY reader thread started")

        try:
            while True:
                state = self._get_state_sync()
                if state not in (TerminalState.INITIALIZING, TerminalState.RUNNING):
                    break

                if not self.pty_fd:
                    break

                try:
                    # Use select with timeout for non-blocking read
                    ready, _, error = select.select(
                        [self.pty_fd], [], [self.pty_fd], 0.1
                    )

                    if error:
                        logger.warning("PTY file descriptor error detected")
                        break

                    if ready:
                        data = os.read(self.pty_fd, 4096)
                        if not data:
                            logger.debug("PTY EOF detected")
                            break

                        # Decode and process output (Issue #315 - use helper)
                        self._process_pty_data(data)

                except OSError as e:
                    if e.errno in (9, 5):  # Bad file descriptor or I/O error
                        logger.debug("PTY closed")
                        break
                    logger.error("PTY read error: %s", e)
                    break
                except Exception as e:
                    logger.error("Unexpected error in PTY reader: %s", e)
                    _increment_stat_sync(self._stats_lock, self.stats, "errors")
                    break

        except Exception as e:
            logger.error("PTY reader thread crashed: %s", e)
        finally:
            # Signal output sender to stop
            self._queue_message_safely({"type": "pty_stopped"})
            logger.debug("PTY reader thread stopped")

    def _get_state_sync(self) -> TerminalState:
        """Get state synchronously for use in threads."""
        return self._state

    def _process_pty_data(self, data: bytes) -> None:
        """Process PTY data and queue output message (Issue #315: extracted)."""
        try:
            output = _decode_and_process_output(data, self.output_processor)
            message = {
                "type": "output",
                "content": output,
                "timestamp": time.time(),
            }
            self._queue_message_safely(message)
        except Exception as e:
            logger.error("Error processing PTY output: %s", e)
            _increment_stat_sync(self._stats_lock, self.stats, "errors")

    def _queue_message_safely(self, message: Dict[str, Any]):
        """Queue message with proper overflow handling."""
        try:
            self.output_queue.put_nowait(message)
        except queue.Full:
            # Drop oldest message to prevent blocking
            try:
                self.output_queue.get_nowait()
                self.output_queue.put_nowait(message)
                logger.warning("Output queue overflow, dropped message")
            except queue.Empty:
                logger.debug("Queue empty during overflow handling")

    async def _send_websocket_message(
        self, message: Dict[str, Any], state: TerminalState
    ) -> None:
        """Send message via WebSocket if conditions are met (Issue #315: extracted).

        Args:
            message: Message to send
            state: Current terminal state
        """
        if not (
            self.message_sender and self.websocket and state == TerminalState.RUNNING
        ):
            return

        try:
            await self.message_sender(message)
            _increment_stat_sync(self._stats_lock, self.stats, "messages_sent")
        except Exception as e:
            logger.error("Error sending message: %s", e)
            _increment_stat_sync(self._stats_lock, self.stats, "errors")

    async def _get_next_queue_message(self) -> Optional[Dict[str, Any]]:
        """Get next message from queue with timeout (Issue #315: extracted).

        Returns:
            Message dict or None if timeout/empty
        """
        try:
            return await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self.output_queue.get, True, 0.1
                ),
                timeout=0.2,
            )
        except (asyncio.TimeoutError, queue.Empty):
            return None

    async def _output_sender_loop(self):
        """Async loop to send queued messages to WebSocket (Issue #315: reduced nesting)."""
        logger.debug("Output sender loop started")

        try:
            while True:
                state = await self.get_state()
                if state == TerminalState.STOPPED:
                    break

                try:
                    message = await self._get_next_queue_message()
                    if message is None:
                        continue

                    if message.get("type") == "pty_stopped":
                        logger.debug("PTY stopped signal received")
                        break

                    await self._send_websocket_message(message, state)

                except Exception as e:
                    logger.error("Error in output sender loop: %s", e)
                    _increment_stat_sync(self._stats_lock, self.stats, "errors")

        except Exception as e:
            logger.error("Output sender loop crashed: %s", e)
        finally:
            logger.debug("Output sender loop stopped")

    async def send_input(self, text: str):
        """Send input to terminal with proper state checking."""
        state = await self.get_state()
        if state != TerminalState.RUNNING:
            raise RuntimeError(f"Cannot send input in state: {state.value}")

        if not self.pty_fd:
            raise RuntimeError("PTY not available")

        try:
            # Apply custom input processing if available
            processed_input = text
            if self.input_processor:
                processed_input = self.input_processor(text)

            # Write to PTY in executor to avoid blocking
            await asyncio.get_event_loop().run_in_executor(
                None, os.write, self.pty_fd, processed_input.encode("utf-8")
            )

            with self._stats_lock:
                self.stats["messages_received"] += 1

        except Exception as e:
            logger.error("Error sending input to PTY: %s", e)
            with self._stats_lock:
                self.stats["errors"] += 1
            raise

    async def stop_session(self):
        """Stop terminal session gracefully."""
        state = await self.get_state()
        if state in (TerminalState.STOPPED, TerminalState.STOPPING):
            return

        await self._set_state(TerminalState.STOPPING)
        logger.info("Stopping terminal session: %s", self.terminal_type)

        try:
            await self._cleanup_resources()
        except Exception as e:
            logger.error("Error during cleanup: %s", e)
        finally:
            await self._set_state(TerminalState.STOPPED)
            logger.info("Terminal session stopped")

    async def _cleanup_resources(self):
        """Clean up all resources with proper synchronization."""
        # Stop background tasks first
        if self.output_sender_task and not self.output_sender_task.done():
            self.output_sender_task.cancel()
            try:
                await asyncio.wait_for(self.output_sender_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.debug("Output sender task cancelled or timed out during cleanup")

        # Wait for reader thread to finish
        if self.reader_thread and self.reader_thread.is_alive():
            try:
                # Give thread time to stop gracefully
                self.reader_thread.join(timeout=2.0)
                if self.reader_thread.is_alive():
                    logger.warning("Reader thread did not stop gracefully")
            except Exception as e:
                logger.warning("Error joining reader thread: %s", e)

        # Clean up PTY
        if self.pty_fd:
            try:
                os.close(self.pty_fd)
            except OSError as e:
                logger.debug("PTY fd close error: %s", e)
            self.pty_fd = None

        # Clean up process (Issue #315 - use helper)
        if self.process:
            _terminate_process_with_fallback(self.process)
            self.process = None

        # Clear output queue
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break

        # Clear WebSocket reference
        self.websocket = None

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics (thread-safe)."""
        # Copy stats and state under lock
        with self._stats_lock:
            stats = self.stats.copy()
            state_value = self._state.value

        if stats["start_time"]:
            stats["uptime"] = time.time() - stats["start_time"]
        else:
            stats["uptime"] = 0

        stats["state"] = state_value
        stats["queue_size"] = self.output_queue.qsize()
        stats["reader_thread_alive"] = (
            self.reader_thread.is_alive() if self.reader_thread else False
        )
        stats["output_task_active"] = (
            not self.output_sender_task.done() if self.output_sender_task else False
        )

        return stats


# Integration helper for existing terminal handlers
class TerminalWebSocketAdapter:
    """
    Adapter to integrate TerminalWebSocketManager with existing terminal classes.
    Provides backwards compatibility while fixing race conditions.
    """

    def __init__(self, terminal_handler, terminal_type: str = "terminal"):
        """Initialize adapter with existing terminal handler."""
        self.handler = terminal_handler
        self.manager = TerminalWebSocketManager(terminal_type)

        # Set up message sender
        self.manager.set_message_sender(self._send_message_to_handler)

        # Set up processors if handler has them
        if hasattr(terminal_handler, "process_input"):
            self.manager.set_input_processor(
                lambda text: asyncio.run(terminal_handler.process_input(text))
            )

        if hasattr(terminal_handler, "process_output"):
            self.manager.set_output_processor(terminal_handler.process_output)

    async def _send_message_to_handler(self, message: Dict[str, Any]):
        """Send message through the terminal handler."""
        if hasattr(self.handler, "send_message"):
            await self.handler.send_message(message)

    async def start_session(self, websocket):
        """Start terminal session through manager."""
        return await self.manager.start_session(websocket)

    async def send_input(self, text: str):
        """Send input through manager."""
        return await self.manager.send_input(text)

    async def stop_session(self):
        """Stop session through manager."""
        return await self.manager.stop_session()

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        return self.manager.get_stats()
