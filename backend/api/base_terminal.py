"""
Base Terminal WebSocket Handler
Provides common terminal functionality for websocket handlers including PTY management
"""

import asyncio
import logging
import os
import pty
import subprocess
import threading
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class BaseTerminalWebSocket(ABC):
    """Base class for terminal WebSocket handlers with consolidated PTY management"""

    def __init__(self):
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
        pass

    @property
    @abstractmethod
    def terminal_type(self) -> str:
        """Get terminal type for logging"""
        pass

    async def start_pty_shell(self):
        """Start a PTY shell process - consolidated implementation"""
        try:
            # Create PTY
            master_fd, slave_fd = pty.openpty()
            self.pty_fd = master_fd

            # Start shell process with PTY
            self.process = subprocess.Popen(
                ["/bin/bash"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.current_dir,
                env=self.env,
                preexec_fn=os.setsid,
            )

            # Close slave fd (process has it)
            os.close(slave_fd)

            # Start reader thread
            self.reader_thread = threading.Thread(
                target=self._read_pty_output, daemon=True
            )
            self.reader_thread.start()

            logger.info(f"PTY shell started for {self.terminal_type}")

        except Exception as e:
            logger.error(f"Failed to start PTY shell: {e}")
            await self.send_message(
                {
                    "type": "error",
                    "message": f"Failed to start {self.terminal_type}: {str(e)}",
                }
            )

    def _read_pty_output(self):
        """Read output from PTY in separate thread - consolidated implementation"""
        import select

        try:
            while self.active and self.pty_fd:
                try:
                    # Read with timeout
                    ready, _, _ = select.select([self.pty_fd], [], [], 0.1)

                    if ready:
                        data = os.read(self.pty_fd, 1024)
                        if data:
                            try:
                                output = data.decode("utf-8", errors="replace")

                                # Call hook for processing output
                                processed_output = self.process_output(output)

                                # Send to WebSocket via async context
                                if self.websocket and self.active:
                                    try:
                                        # Get the current event loop or create new one
                                        try:
                                            loop = asyncio.get_event_loop()
                                            if loop.is_running():
                                                # Use run_coroutine_threadsafe
                                                asyncio.run_coroutine_threadsafe(
                                                    self.send_message(
                                                        {
                                                            "type": "output",
                                                            "data": processed_output,
                                                        }
                                                    ),
                                                    loop,
                                                )
                                            else:
                                                # Loop not running, run directly
                                                loop.run_until_complete(
                                                    self.send_message(
                                                        {
                                                            "type": "output",
                                                            "data": processed_output,
                                                        }
                                                    )
                                                )
                                        except RuntimeError:
                                            # No event loop, create new one
                                            loop = asyncio.new_event_loop()
                                            asyncio.set_event_loop(loop)
                                            loop.run_until_complete(
                                                self.send_message(
                                                    {
                                                        "type": "output",
                                                        "data": processed_output,
                                                    }
                                                )
                                            )
                                            loop.close()
                                    except Exception as e:
                                        logger.error(f"Error sending PTY output: {e}")
                            except Exception as e:
                                logger.error(f"Error processing PTY data: {e}")
                        else:
                            # PTY closed
                            break
                except OSError:
                    break
                except Exception as e:
                    logger.error(f"Error reading PTY: {e}")
                    break
        except Exception as e:
            logger.error(f"PTY reader thread error: {e}")

    def process_output(self, output: str) -> str:
        """Process PTY output before sending - override in subclasses"""
        return output

    async def send_input(self, text: str):
        """Send input to PTY shell - consolidated implementation"""
        if self.pty_fd and self.active:
            try:
                # Call hook for processing input (override in subclasses)
                processed_input = await self.process_input(text)
                os.write(self.pty_fd, processed_input.encode("utf-8"))
            except Exception as e:
                logger.error(f"Error writing to PTY: {e}")

    async def process_input(self, text: str) -> str:
        """Process input before sending to PTY - override in subclasses"""
        return text

    async def cleanup(self):
        """Clean up PTY resources - consolidated implementation"""
        logger.info(f"Cleaning up {self.terminal_type} session")

        self.active = False

        # Close PTY file descriptor
        if self.pty_fd:
            try:
                os.close(self.pty_fd)
            except OSError:
                pass
            self.pty_fd = None

        # Terminate process
        if self.process:
            try:
                self.process.terminate()
                # Give process time to terminate gracefully
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            except OSError:
                pass
            self.process = None

        # Wait for reader thread to finish
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1)

        self.reader_thread = None

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
