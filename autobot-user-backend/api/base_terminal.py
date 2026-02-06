"""
Base Terminal WebSocket Handler
Provides common terminal functionality for websocket handlers including PTY management
Updated to use improved TerminalWebSocketManager for race condition fixes
"""

import asyncio
import logging
import os
import subprocess  # nosec B404 - required for PTY terminal operations
import threading
from abc import ABC, abstractmethod
from typing import Optional

from utils.terminal_websocket_manager import TerminalWebSocketAdapter

logger = logging.getLogger(__name__)


class BaseTerminalWebSocket(ABC):
    """Base class for terminal WebSocket handlers with improved race condition handling"""

    def __init__(self):
        # Use new terminal manager for race condition fixes
        self.terminal_adapter = TerminalWebSocketAdapter(self, self.terminal_type)

        # Legacy compatibility properties
        self.websocket = None
        self.pty_fd: Optional[int] = None
        self.process: Optional[subprocess.Popen] = None
        self.reader_thread: Optional[threading.Thread] = None
        self.active = False
        self.current_dir = "/home/kali"
        self.env = os.environ.copy()

    @abstractmethod
    async def send_message(self, message: dict):
        """Send message to WebSocket client"""

    @property
    @abstractmethod
    def terminal_type(self) -> str:
        """Get terminal type for logging"""

    async def start_pty_shell(self):
        """Start a PTY shell process using improved terminal manager"""
        try:
            self.active = True
            await self.terminal_adapter.start_session(self.websocket)

            # Update legacy properties for compatibility
            self.pty_fd = self.terminal_adapter.manager.pty_fd
            self.process = self.terminal_adapter.manager.process

            logger.info(f"PTY shell started for {self.terminal_type}")

        except Exception as e:
            self.active = False
            logger.error(f"Failed to start PTY shell: {e}")
            await self.send_message(
                {
                    "type": "error",
                    "message": f"Failed to start {self.terminal_type}: {str(e)}",
                }
            )

    def _initialize_output_sender(self):
        """Initialize async output sender task. Issue #620.

        Sets up the output queue and schedules the async sender coroutine.
        """
        import queue

        # Create output queue for thread-safe message passing
        self.output_queue = queue.Queue()

        # Cancel existing sender task if any
        if hasattr(self, "_output_sender_task"):
            self._output_sender_task.cancel()

        # Schedule async output sender
        try:
            loop = asyncio.get_event_loop()
            self._output_sender_task = asyncio.run_coroutine_threadsafe(
                self._async_output_sender(), loop
            )
        except RuntimeError:
            # No loop available - will handle synchronously
            self._output_sender_task = None

    def _process_and_queue_pty_data(self, data: bytes) -> bool:
        """Process PTY data and queue message for delivery. Issue #620.

        Args:
            data: Raw bytes from PTY

        Returns:
            True if processing succeeded, False if PTY closed
        """
        import queue
        import time

        if not data:
            return False

        try:
            output = data.decode("utf-8", errors="replace")
            processed_output = self.process_output(output)

            message = {
                "type": "output",
                "content": processed_output,
                "timestamp": time.time(),
            }

            try:
                self.output_queue.put_nowait(message)
            except queue.Full:
                # Queue is full, drop oldest message to prevent blocking
                try:
                    self.output_queue.get_nowait()
                    self.output_queue.put_nowait(message)
                except queue.Empty:
                    pass

        except Exception as e:
            logger.error(f"Error processing PTY data: {e}")

        return True

    def _signal_output_sender_stop(self):
        """Signal async output sender to stop. Issue #620."""
        import queue

        if hasattr(self, "output_queue"):
            try:
                self.output_queue.put_nowait({"type": "stop"})
            except queue.Full:
                pass

    def _read_pty_output(self):
        """Read output from PTY in separate thread with queue-based delivery."""
        import select

        self._initialize_output_sender()

        try:
            while self.active and self.pty_fd:
                try:
                    ready, _, _ = select.select([self.pty_fd], [], [], 0.1)

                    if ready:
                        data = os.read(self.pty_fd, 1024)
                        if not self._process_and_queue_pty_data(data):
                            break
                except OSError:
                    break
                except Exception as e:
                    logger.error(f"Error reading PTY: {e}")
                    break
        except Exception as e:
            logger.error(f"PTY reader thread error: {e}")
        finally:
            self._signal_output_sender_stop()

    async def _async_output_sender(self):
        """Async task to send queued output messages to WebSocket"""
        import queue

        if not hasattr(self, "output_queue"):
            return

        try:
            while self.active:
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, self.output_queue.get, True, 0.1
                        ),
                        timeout=0.2,
                    )

                    if message.get("type") == "stop":
                        break

                    # Send message if WebSocket is active
                    if self.websocket and self.active:
                        await self.send_message(message)

                except asyncio.TimeoutError:
                    continue
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error in async output sender: {e}")

        except Exception as e:
            logger.error(f"Async output sender error: {e}")

    def process_output(self, output: str) -> str:
        """Process PTY output before sending - override in subclasses"""
        return output

    async def send_input(self, text: str):
        """Send input to PTY shell using improved terminal manager"""
        if self.active:
            try:
                await self.terminal_adapter.send_input(text)
            except Exception as e:
                logger.error(f"Error writing to PTY: {e}")

    async def process_input(self, text: str) -> str:
        """Process input before sending to PTY - override in subclasses"""
        return text

    async def cleanup(self):
        """Clean up PTY resources - consolidated implementation"""
        logger.info(f"Cleaning up {self.terminal_type} session")

        self.active = False

        # Cancel async output sender task
        if hasattr(self, "_output_sender_task") and self._output_sender_task:
            try:
                self._output_sender_task.cancel()
                # Wait for task to complete cancellation
                try:
                    await asyncio.wait_for(
                        asyncio.wrap_future(self._output_sender_task), timeout=1.0
                    )
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
            except Exception as e:
                logger.warning(f"Error cancelling output sender task: {e}")

        # Clear output queue
        if hasattr(self, "output_queue"):
            try:
                # Drain the queue
                while not self.output_queue.empty():
                    try:
                        self.output_queue.get_nowait()
                    except Exception:
                        break
            except Exception as e:
                logger.warning(f"Error clearing output queue: {e}")

        # Use new terminal manager for cleanup
        try:
            await self.terminal_adapter.stop_session()

            # Clear legacy properties
            self.pty_fd = None
            self.process = None
            self.reader_thread = None
            self.websocket = None

        except Exception as e:
            logger.error(f"Error during improved cleanup: {e}")

        logger.info(f"{self.terminal_type} cleanup completed")

    async def execute_command(self, command: str) -> bool:
        """Send command to PTY shell with common handling"""
        if not command.strip():
            return False

        logger.info(f"{self.terminal_type} executing: {command}")

        try:
            # Send command to PTY shell
            await self.send_input(command + "\n")
            return True

        except Exception as e:
            logger.error(f"{self.terminal_type} command error: {e}")
            await self.send_message(
                {"type": "error", "message": f"{self.terminal_type} error: {str(e)}"}
            )
            return False

    async def validate_command(self, command: str) -> bool:
        """Validate command before execution (override in subclasses)"""
        return True

    def get_terminal_stats(self) -> dict:
        """Get terminal session statistics"""
        try:
            return self.terminal_adapter.get_stats()
        except Exception as e:
            logger.error(f"Error getting terminal stats: {e}")
            return {"error": str(e)}
