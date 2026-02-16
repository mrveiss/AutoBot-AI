# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Terminal Command Executor

Handles command execution in PTY with intelligent polling and cancellation.
"""

import asyncio
import logging
import re
import time
import uuid
from typing import Optional

from backend.constants.path_constants import PATH
from backend.constants.threshold_constants import TimingConstants
from backend.type_defs.common import Metadata
from backend.utils.encoding_utils import strip_ansi_codes

from .models import AgentTerminalSession

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for error detection patterns
_ERROR_PATTERNS = (
    r"command not found",
    r"permission denied",
    r"no such file or directory",
    r"cannot access",
    r"error:",
    r"fatal:",
    r"failed",
)


def _extract_terminal_output(messages: list) -> str:
    """Extract most recent terminal output from messages (Issue #315: extracted).

    Returns:
        Cleaned output string or empty string if none found
    """
    for msg in reversed(messages):
        if msg.get("sender") != "terminal" or not msg.get("text"):
            continue
        terminal_text = msg["text"]
        clean_output = strip_ansi_codes(terminal_text)

        # Extract output (skip command echo)
        lines = clean_output.split("\n")
        if len(lines) > 1:
            return "\n".join(lines[1:]).strip()
        return ""
    return ""


class CommandExecutor:
    """Executes commands in PTY with intelligent polling"""

    def __init__(self, chat_history_manager=None):
        """
        Initialize command executor.

        Args:
            chat_history_manager: ChatHistoryManager instance for output polling
        """
        self.chat_history_manager = chat_history_manager

    def _send_sigint_to_pty(self, session: AgentTerminalSession) -> bool:
        """
        Send SIGINT (Ctrl+C) to PTY for graceful command termination.

        Issue #281: Extracted from cancel_command to reduce function length
        and improve testability of signal handling logic.

        Args:
            session: Agent terminal session

        Returns:
            True if SIGINT was sent successfully, False otherwise
        """
        try:
            self._write_to_pty(session, "\x03")  # Ctrl+C
            logger.info(
                f"[CANCEL] Sent SIGINT (Ctrl+C) to PTY {session.pty_session_id}"
            )
            return True
        except Exception as sigint_error:
            logger.warning("[CANCEL] Failed to send SIGINT: %s", sigint_error)
            return False

    async def _log_cancellation_to_chat(
        self, session: AgentTerminalSession, reason: str
    ) -> None:
        """
        Log command cancellation to chat history.

        Issue #281: Extracted from cancel_command to reduce function length
        and separate logging concerns.

        Args:
            session: Agent terminal session
            reason: Reason for cancellation
        """
        if not session.has_conversation() or not self.chat_history_manager:
            return

        try:
            await self.chat_history_manager.add_message(
                sender="system",
                text=f"⚠️ Command cancelled due to {reason}",
                message_type="command_cancellation",
                session_id=session.conversation_id,
                metadata=session.get_cancellation_metadata(reason),
            )
            logger.info("[CANCEL] Logged cancellation to chat history")
        except Exception as log_error:
            logger.warning(f"[CANCEL] Failed to log cancellation to chat: {log_error}")

    def _force_close_pty_session(self, pty_session_id: str) -> bool:
        """
        Forcefully close PTY session with SIGKILL (Issue #665: extracted helper).

        Args:
            pty_session_id: PTY session identifier

        Returns:
            True if closed successfully, False otherwise
        """
        from backend.services.simple_pty import simple_pty_manager

        try:
            simple_pty_manager.close_session(pty_session_id)
            logger.info(f"[CANCEL] Forcefully closed PTY session {pty_session_id}")
            return True
        except Exception as sigkill_error:
            logger.error(f"[CANCEL] Failed to forcefully close PTY: {sigkill_error}")
            return False

    async def _finalize_cancellation(
        self, session: AgentTerminalSession, reason: str
    ) -> bool:
        """
        Finalize command cancellation with cleanup and logging.

        Issue #665: Extracted from cancel_command to reduce function length.

        Args:
            session: Agent terminal session
            reason: Reason for cancellation

        Returns:
            True if finalization completed successfully
        """
        # Clean up session state (Issue #372 - use model method)
        task_was_running = await session.cancel_running_task()
        if task_was_running:
            logger.info(
                f"[CANCEL] Cancelled running command task for "
                f"session {session.session_id}"
            )

        # Log cancellation (Issue #281: uses extracted helper)
        await self._log_cancellation_to_chat(session, reason)

        logger.info(
            f"[CANCEL] ✅ Command cancellation complete for "
            f"session {session.session_id}"
        )
        return True

    def _write_to_pty(self, session: AgentTerminalSession, text: str) -> bool:
        """
        Write text to PTY terminal display.
        Auto-recreates PTY if stale (e.g., after backend restart).

        Args:
            session: Agent terminal session
            text: Text to write to terminal

        Returns:
            True if written successfully
        """
        logger.info(
            f"[PTY_WRITE] Called for session {session.session_id}, "
            f"pty_session_id={session.pty_session_id}, text_len={len(text)}"
        )

        if not session.pty_session_id:
            logger.warning("No PTY session ID available for writing")
            return False

        try:
            from backend.services.simple_pty import simple_pty_manager

            pty = simple_pty_manager.get_session(session.pty_session_id)
            logger.info(
                f"[PTY_WRITE] Got PTY session: {pty is not None}, "
                f"alive: {pty.is_alive() if pty else 'N/A'}"
            )

            # If PTY is not alive, recreate it (handles stale sessions after restart)
            if not pty or not pty.is_alive():
                logger.warning(
                    f"[PTY_WRITE] PTY session {session.pty_session_id} not alive "
                    f"(exists={pty is not None}), recreating..."
                )

                # Create new PTY with same session ID
                new_pty = simple_pty_manager.create_session(
                    session.pty_session_id, initial_cwd=str(PATH.PROJECT_ROOT)
                )

                if new_pty:
                    logger.info("Recreated PTY session %s", session.pty_session_id)
                    pty = new_pty
                else:
                    logger.error(
                        f"Failed to recreate PTY session {session.pty_session_id}"
                    )
                    return False

            # Write to PTY
            success = pty.write_input(text)
            if success:
                logger.debug(
                    "Wrote to PTY %s: %s...", session.pty_session_id, text[:50]
                )
            return success

        except Exception as e:
            logger.error("Error writing to PTY: %s", e)
            return False

    async def cancel_command(
        self, session: AgentTerminalSession, reason: str = "timeout"
    ) -> bool:
        """
        Cancel a running command with graceful shutdown.

        Issue #665: Refactored to use extracted helpers for SIGINT and SIGKILL operations.

        CRITICAL FIX (Critical #3): Proper cleanup for timeouts to prevent orphaned processes.

        Process:
        1. Send SIGTERM to gracefully stop the process
        2. Wait 2-3 seconds for graceful shutdown
        3. Send SIGKILL if still running
        4. Clean up resources and log the cancellation

        Args:
            session: Agent terminal session
            reason: Reason for cancellation (default: "timeout")

        Returns:
            True if command was cancelled successfully
        """
        if not session.has_pty_session():
            logger.warning(
                f"[CANCEL] No PTY session to cancel for {session.session_id}"
            )
            return False

        try:
            from backend.services.simple_pty import simple_pty_manager

            pty = simple_pty_manager.get_session(session.pty_session_id)
            if not pty or not pty.is_alive():
                logger.info(
                    f"[CANCEL] PTY session {session.pty_session_id} not alive, "
                    f"nothing to cancel"
                )
                return False

            logger.warning(
                f"[CANCEL] Cancelling command due to {reason}: "
                f"PTY {session.pty_session_id}"
            )

            # Issue #281: Step 1 - Send SIGINT using extracted helper
            self._send_sigint_to_pty(session)

            # Step 2: Wait for graceful shutdown
            await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)

            # Step 3: Check if process is still running (Issue #665: uses helper)
            if pty.is_alive():
                logger.warning(
                    "[CANCEL] Process still running after SIGINT, "
                    "attempting forceful termination (SIGKILL)"
                )
                if not self._force_close_pty_session(session.pty_session_id):
                    return False
            else:
                logger.info("[CANCEL] Process terminated gracefully after SIGINT")

            # Steps 4-5: Cleanup and finalize (Issue #665: extracted helper)
            return await self._finalize_cancellation(session, reason)

        except Exception as e:
            logger.error(
                "[CANCEL] Error during command cancellation: %s", e, exc_info=True
            )
            return False

    def _search_for_exit_marker(
        self, messages: list, marker: str, marker_id: str
    ) -> Optional[int]:
        """Search messages for exit code marker. (Issue #315 - extracted)"""
        escaped_marker = re.escape(marker)
        for msg in reversed(messages):
            if msg.get("sender") != "terminal" or not msg.get("text"):
                continue
            clean_text = strip_ansi_codes(msg["text"])
            match = re.search(rf"{escaped_marker}(\d+)", clean_text)
            if match:
                return_code = int(match.group(1))
                logger.info(
                    f"[PTY_EXEC] Detected return code: {return_code} "
                    f"(marker: {marker_id})"
                )
                return return_code
        return None

    async def _detect_return_code(
        self, session: AgentTerminalSession, max_attempts: int = 10
    ) -> Optional[int]:
        """
        Detect command return code using exit code marker injection.

        SECURITY FIX (Critical #2): Uses UUID-based marker to prevent regex injection.
        Phase 1 Implementation: Injects unique marker and polls chat history with
        exponential backoff to detect the exit code.

        Args:
            session: Agent terminal session
            max_attempts: Maximum polling attempts (default: 10)

        Returns:
            Return code if detected, None if detection failed
        """
        if not self.chat_history_manager:
            return None

        logger.debug("[PTY_EXEC] Injecting exit code marker...")

        # SECURITY FIX (Critical #2): Generate unique UUID-based marker to prevent spoofing
        # Attack vector fixed: `echo "EXIT_CODE:0" && malicious_command` can no longer fake success
        marker_id = str(uuid.uuid4())
        marker = f"__EXIT_CODE_{marker_id}__:"

        # Inject marker to capture exit code
        marker_cmd = f"echo '{marker}'$?"
        if not self._write_to_pty(session, f"{marker_cmd}\n"):
            logger.warning("[PTY_EXEC] Failed to inject exit code marker")
            return None

        logger.debug("[PTY_EXEC] Injected unique marker: %s", marker)

        # Poll with exponential backoff
        base_delay = TimingConstants.MICRO_DELAY  # Start with 100ms
        for attempt in range(max_attempts):
            await asyncio.sleep(base_delay * (1.5**attempt))  # Exponential backoff

            if not session.conversation_id:
                continue

            try:
                messages = await self.chat_history_manager.get_session_messages(
                    session_id=session.conversation_id, limit=3
                )
                # Use helper to search for marker (Issue #315)
                result = self._search_for_exit_marker(messages, marker, marker_id)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning(
                    f"[PTY_EXEC] Error detecting return code "
                    f"(attempt {attempt + 1}): {e}"
                )

        # Fallback: Analyze error patterns
        logger.debug(
            "[PTY_EXEC] Marker detection failed, falling back to error pattern analysis"
        )
        return await self._analyze_error_patterns(session)

    def _check_error_patterns_in_text(
        self, clean_text: str, error_patterns: list
    ) -> bool:
        """Check if text contains any error patterns. (Issue #315 - extracted)"""
        for pattern in error_patterns:
            if re.search(pattern, clean_text):
                logger.debug("[PTY_EXEC] Error pattern detected: %s", pattern)
                return True
        return False

    async def _analyze_error_patterns(self, session: AgentTerminalSession) -> int:
        """
        Fallback return code detection via error pattern analysis.

        Analyzes recent terminal output for common error indicators when
        exit code marker detection fails.

        Args:
            session: Agent terminal session

        Returns:
            Return code estimate (0 = success, 1 = error)
        """
        if not self.chat_history_manager:
            return 0

        # Issue #380: use module-level constant
        try:
            if not session.conversation_id:
                return 0  # Assume success if no conversation

            messages = await self.chat_history_manager.get_session_messages(
                session_id=session.conversation_id, limit=5
            )

            for msg in reversed(messages):
                if msg.get("sender") != "terminal" or not msg.get("text"):
                    continue
                clean_text = strip_ansi_codes(msg["text"]).lower()
                # Use helper to check patterns (Issue #315, #380: use module constant)
                if self._check_error_patterns_in_text(clean_text, _ERROR_PATTERNS):
                    return 1  # Error detected

        except Exception as e:
            logger.warning("[PTY_EXEC] Error pattern analysis failed: %s", e)

        return 0  # Assume success if no errors detected

    async def _poll_for_current_output(self, session: AgentTerminalSession) -> str:
        """
        Poll chat history for current terminal output (Issue #665: extracted helper).

        Args:
            session: Agent terminal session

        Returns:
            Current terminal output or empty string
        """
        if not session.conversation_id or not self.chat_history_manager:
            return ""

        try:
            messages = await self.chat_history_manager.get_session_messages(
                session_id=session.conversation_id, limit=5
            )
            return _extract_terminal_output(messages)
        except Exception as e:
            logger.warning("[PTY_EXEC] Polling error: %s", e)
            return ""

    async def _handle_poll_timeout(
        self, session: AgentTerminalSession, elapsed: float, last_output: str
    ) -> str:
        """
        Handle polling timeout with command cancellation (Issue #665: extracted helper).

        CRITICAL FIX (Critical #3): Cancels command to prevent orphaned processes.

        Args:
            session: Agent terminal session
            elapsed: Elapsed time in seconds
            last_output: Last captured output

        Returns:
            Last captured output
        """
        logger.warning(
            f"[PTY_EXEC] Polling timeout reached ({elapsed:.2f}s), "
            f"cancelling command to prevent orphaned processes"
        )

        cancelled = await self.cancel_command(session, reason="timeout")
        if cancelled:
            logger.info("[PTY_EXEC] Successfully cancelled command after timeout")
        else:
            logger.error(
                "[PTY_EXEC] Failed to cancel command after timeout - "
                "may have orphaned process"
            )

        return last_output

    async def _intelligent_poll_output(
        self,
        session: AgentTerminalSession,
        timeout: float = 30.0,
        stability_threshold: float = 0.5,
    ) -> str:
        """
        Intelligent polling system with adaptive timeouts and output stability detection.

        Issue #665: Refactored to use extracted helpers for polling and timeout handling.

        CRITICAL FIX (Critical #3): Cancels command on timeout to prevent orphaned processes.
        Phase 2 Implementation: Polls chat history with progressive backoff until
        output stabilizes (unchanged for stability_threshold seconds) or timeout.

        Args:
            session: Agent terminal session
            timeout: Maximum wait time in seconds (default: 30s)
            stability_threshold: Seconds of unchanged output to consider stable (default: 0.5s)

        Returns:
            Collected output from chat history
        """
        if not self.chat_history_manager:
            return ""

        start_time = time.time()
        last_output = ""
        last_change_time = start_time
        poll_interval = 0.1  # Start with 100ms
        max_interval = 2.0  # Cap at 2 seconds

        logger.debug(
            f"[PTY_EXEC] Starting intelligent polling "
            f"(timeout={timeout}s, stability={stability_threshold}s)"
        )

        while (time.time() - start_time) < timeout:
            # Poll for current output (Issue #665: uses helper)
            current_output = await self._poll_for_current_output(session)

            # Check output stability
            if current_output and current_output == last_output:
                stable_duration = time.time() - last_change_time
                if stable_duration >= stability_threshold:
                    logger.info(
                        f"[PTY_EXEC] Output stabilized after {stable_duration:.2f}s, "
                        f"total elapsed: {time.time() - start_time:.2f}s"
                    )
                    return current_output
            elif current_output != last_output:
                last_output = current_output
                last_change_time = time.time()
                poll_interval = 0.1  # Reset interval on new output

            # Progressive backoff
            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, max_interval)

        # Timeout reached - handle with cancellation (Issue #665: uses helper)
        elapsed = time.time() - start_time
        return await self._handle_poll_timeout(session, elapsed, last_output)

    def _build_pty_error_result(self, error_msg: str) -> Metadata:
        """
        Build error result for PTY command execution failure.

        Issue #665: Extracted from execute_in_pty to reduce function length.

        Args:
            error_msg: Error message describing the failure

        Returns:
            Dict with error status, empty stdout, error stderr, and return code 1
        """
        return {
            "status": "error",
            "stdout": "",
            "stderr": error_msg,
            "return_code": 1,
        }

    def _build_pty_result(self, output: str, return_code: int) -> Metadata:
        """
        Build result dict for PTY command execution.

        Issue #665: Extracted from execute_in_pty to reduce function length.

        Args:
            output: Command output from PTY
            return_code: Command return code

        Returns:
            Dict with status, stdout, stderr, and return_code
        """
        return {
            "status": "success" if return_code == 0 else "error",
            "stdout": output,
            "stderr": "",  # PTY combines stdout/stderr
            "return_code": return_code,
        }

    async def _poll_and_detect_return_code(
        self, session: AgentTerminalSession, timeout: float
    ) -> tuple[str, int]:
        """
        Poll for command output and detect return code.

        Issue #665: Extracted from execute_in_pty to reduce function length.
        Implements the pub/sub pattern via chat history to avoid race conditions.

        Args:
            session: Agent terminal session
            timeout: Max seconds to wait for output

        Returns:
            Tuple of (full_output, return_code)
        """
        # Phase 2: Intelligent polling with adaptive timeouts
        logger.info(
            f"[PTY_EXEC] Starting intelligent polling (timeout={timeout}s) "
            f"for command completion..."
        )

        full_output = await self._intelligent_poll_output(
            session=session,
            timeout=timeout,
            stability_threshold=0.5,  # 500ms stability threshold
        )

        # Phase 1: Detect return code with retry logic
        return_code = await self._detect_return_code(
            session=session,
            max_attempts=10,
        )

        # If detection failed, default to 0 (success) or analyze errors
        if return_code is None:
            logger.warning("[PTY_EXEC] Return code detection failed, using fallback")
            return_code = 0 if full_output else 1

        logger.info(
            f"[PTY_EXEC] Command execution complete. "
            f"Return code: {return_code}, Output length: {len(full_output)} chars"
        )

        return full_output, return_code

    async def execute_in_pty(
        self, session: AgentTerminalSession, command: str, timeout: float = 30.0
    ) -> Metadata:
        """
        Execute command directly in PTY shell (true collaboration mode).

        Issue #665: Refactored to use helper methods for result building.

        Args:
            session: Agent terminal session
            command: Command to execute
            timeout: Max seconds to wait for output (default: 30s)

        Returns:
            Dict with status, stdout, stderr, return_code
        """
        logger.info("[PTY_EXEC] Executing in PTY: %s", command)

        # Write command to PTY (shell will execute it)
        if not self._write_to_pty(session, f"{command}\n"):
            return self._build_pty_error_result("Failed to write command to PTY")

        # Poll for output and detect return code (Issue #665: extracted)
        full_output, return_code = await self._poll_and_detect_return_code(
            session, timeout
        )

        return self._build_pty_result(full_output, return_code)
