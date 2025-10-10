"""
Terminal WebSocket State Manager
Provides thread-safe and race-condition-free terminal WebSocket management
"""

import asyncio
import logging
import os
import pty
import queue
import subprocess
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


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

        # WebSocket and PTY resources
        self.websocket = None
        self.pty_fd: Optional[int] = None
        self.process: Optional[subprocess.Popen] = None

        # Threading resources
        self.reader_thread: Optional[threading.Thread] = None
        self.output_queue: queue.Queue = queue.Queue(maxsize=1000)
        self.output_sender_task: Optional[asyncio.Task] = None

        # Configuration
        self.current_dir = "/home/kali"
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
            self.stats["start_time"] = time.time()

            # Create PTY with proper error handling
            await self._create_pty()

            # Start background tasks
            await self._start_background_tasks()

            await self._set_state(TerminalState.RUNNING)
            logger.info(f"Terminal session started successfully: {self.terminal_type}")

        except Exception as e:
            await self._set_state(TerminalState.ERROR)
            logger.error(f"Failed to start terminal session: {e}")
            await self._cleanup_resources()
            raise

    async def _create_pty(self):
        """Create PTY and start shell process."""
        try:
            # Create PTY pair
            master_fd, slave_fd = pty.openpty()
            self.pty_fd = master_fd

            # Configure PTY settings
            import termios

            attrs = termios.tcgetattr(slave_fd)
            # Disable auto CR/LF and XON/XOFF
            attrs[0] &= ~(termios.ICRNL | termios.IXON)
            attrs[3] &= ~termios.ECHO  # Disable echo
            termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)

            # Start shell process with safer preexec_fn
            def safe_preexec():
                """Safe preexec function that handles errors gracefully"""
                try:
                    os.setsid()
                except OSError as e:
                    # Log but don't fail - some environments don't support setsid
                    logger.warning(f"setsid failed in preexec_fn: {e}")
            
            self.process = subprocess.Popen(
                ["/bin/bash", "-i"],  # Interactive bash
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.current_dir,
                env=self.env,
                preexec_fn=safe_preexec,
                start_new_session=True,
            )

            # Close slave fd (process owns it now)
            os.close(slave_fd)

            # Verify process started
            if self.process.poll() is not None:
                raise RuntimeError("Shell process failed to start")

            logger.debug(f"PTY created: fd={master_fd}, pid={self.process.pid}")

        except Exception as e:
            if "master_fd" in locals():
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            if "slave_fd" in locals():
                try:
                    os.close(slave_fd)
                except OSError:
                    pass
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

                        # Decode and process output
                        try:
                            output = data.decode("utf-8", errors="replace")

                            # Apply custom processing if available
                            if self.output_processor:
                                output = self.output_processor(output)

                            # Queue message for async delivery
                            message = {
                                "type": "output",
                                "content": output,
                                "timestamp": time.time(),
                            }

                            self._queue_message_safely(message)

                        except Exception as e:
                            logger.error(f"Error processing PTY output: {e}")
                            self.stats["errors"] += 1

                except OSError as e:
                    if e.errno in (9, 5):  # Bad file descriptor or I/O error
                        logger.debug("PTY closed")
                        break
                    logger.error(f"PTY read error: {e}")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in PTY reader: {e}")
                    self.stats["errors"] += 1
                    break

        except Exception as e:
            logger.error(f"PTY reader thread crashed: {e}")
        finally:
            # Signal output sender to stop
            self._queue_message_safely({"type": "pty_stopped"})
            logger.debug("PTY reader thread stopped")

    def _get_state_sync(self) -> TerminalState:
        """Get state synchronously for use in threads."""
        return self._state

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
                pass

    async def _output_sender_loop(self):
        """Async loop to send queued messages to WebSocket."""
        logger.debug("Output sender loop started")

        try:
            while True:
                state = await self.get_state()
                if state == TerminalState.STOPPED:
                    break

                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, self.output_queue.get, True, 0.1
                        ),
                        timeout=0.2,
                    )

                    if message.get("type") == "pty_stopped":
                        logger.debug("PTY stopped signal received")
                        break

                    # Send message if we have a sender and are active
                    if (
                        self.message_sender
                        and self.websocket
                        and state == TerminalState.RUNNING
                    ):
                        try:
                            await self.message_sender(message)
                            self.stats["messages_sent"] += 1
                        except Exception as e:
                            logger.error(f"Error sending message: {e}")
                            self.stats["errors"] += 1

                except asyncio.TimeoutError:
                    continue
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error in output sender loop: {e}")
                    self.stats["errors"] += 1

        except Exception as e:
            logger.error(f"Output sender loop crashed: {e}")
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

            self.stats["messages_received"] += 1

        except Exception as e:
            logger.error(f"Error sending input to PTY: {e}")
            self.stats["errors"] += 1
            raise

    async def stop_session(self):
        """Stop terminal session gracefully."""
        state = await self.get_state()
        if state in (TerminalState.STOPPED, TerminalState.STOPPING):
            return

        await self._set_state(TerminalState.STOPPING)
        logger.info(f"Stopping terminal session: {self.terminal_type}")

        try:
            await self._cleanup_resources()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
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
                pass

        # Wait for reader thread to finish
        if self.reader_thread and self.reader_thread.is_alive():
            try:
                # Give thread time to stop gracefully
                self.reader_thread.join(timeout=2.0)
                if self.reader_thread.is_alive():
                    logger.warning("Reader thread did not stop gracefully")
            except Exception as e:
                logger.warning(f"Error joining reader thread: {e}")

        # Clean up PTY
        if self.pty_fd:
            try:
                os.close(self.pty_fd)
            except OSError:
                pass
            self.pty_fd = None

        # Clean up process
        if self.process:
            try:
                # Try graceful termination first
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    self.process.kill()
                    self.process.wait(timeout=1)
            except Exception as e:
                logger.warning(f"Error terminating process: {e}")
            finally:
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
        """Get session statistics."""
        stats = self.stats.copy()
        if stats["start_time"]:
            stats["uptime"] = time.time() - stats["start_time"]
        else:
            stats["uptime"] = 0

        stats["state"] = self._state.value
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
