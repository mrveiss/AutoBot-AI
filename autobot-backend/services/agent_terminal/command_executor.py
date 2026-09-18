# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Terminal Command Executor

Handles command execution in PTY with intelligent polling and cancellation.

A command runs in the session's own shell, followed at once by a UUID-marked
``echo '<marker>'$?`` line (#17074). The shell runs the marker only after the
command returns, so the marker's appearance in the PTY's transcript is the
completion signal and ``$?`` is the command's own exit code, from the same
shell. Output used to be polled from chat history filtered to
``sender == "terminal"``, but agent output is saved as ``agent_terminal`` and
only after the command returns: the poll never saw it, every command waited
out its timeout, and the exit-code marker written afterwards landed in a shell
recreated after the kill, reporting ``EXIT_CODE: 0`` for a command that never
finished. A command that times out is now cancelled and reported as timed out,
and nothing more is written to its PTY.
"""

import asyncio
import re
import time
import uuid

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from constants.path_constants import PATH
from constants.threshold_constants import TimingConstants
from type_defs.common import Metadata
from utils.encoding_utils import strip_ansi_codes

from .models import AgentTerminalSession

logger = get_logger(__name__)

#: Seconds an agent command may run before it is cancelled and reported as timed out (#17074).
AGENT_COMMAND_TIMEOUT_S = env_int("AUTOBOT_AGENT_COMMAND_TIMEOUT_S", 30)

#: Return code reported for a command cancelled on timeout, as timeout(1) reports it.
TIMED_OUT_RETURN_CODE = 124

#: A few of the PTY reader thread's 10 ms poll cycles: output already on the wire at
#: the deadline gets this long to be read before the command is called timed out.
_READER_GRACE_S = 0.05

#: Prefixed to output whose start the transcript cap had already dropped.
TRUNCATED_NOTE = "[earlier output dropped: it exceeded the terminal transcript]\n"


def _command_output(transcript: str, marker: str, echoed_lines: int) -> str:
    """The output after the *echoed_lines* lines the shell echoed back, before the first marker line.

    A multi-line command is echoed one line per line, continuations behind the
    PS2 prompt, so the echo spans as many lines as the command does.
    """
    lines = strip_ansi_codes(transcript).replace("\r", "").split("\n")[echoed_lines:]
    kept = []
    for line in lines:
        if marker in line:  # the prompt that echoes the marker line, or the marker's own output
            break
        kept.append(line)
    return "\n".join(kept).strip()


def _find_exit_code(transcript: str, marker: str) -> int | None:
    """The exit code printed after *marker*, or None if it has not appeared yet."""
    match = re.search(rf"{re.escape(marker)}(\d+)", strip_ansi_codes(transcript))
    return int(match.group(1)) if match else None


def _scan_for_exit_code(pty, cursor: int, marker: str) -> tuple[int, int | None]:
    """Search only output past *cursor* -- plus enough overlap for a marker split across reads.

    Returns the new cursor and the exit code, if it has appeared.
    """
    offset, text = pty.read_transcript(max(cursor - len(marker) - 16, 0))
    return offset + len(text), _find_exit_code(text, marker)


def _output_since(pty, start: int, command: str, marker: str) -> str:
    """The command's output, noting it when the transcript cap already dropped its beginning."""
    offset, transcript = pty.read_transcript(start)
    if offset > start:
        return TRUNCATED_NOTE + _command_output(transcript, marker, echoed_lines=0)
    return _command_output(transcript, marker, echoed_lines=command.count("\n") + 1)


class CommandExecutor:
    """Executes commands in PTY with intelligent polling"""

    def __init__(self, chat_history_manager=None) -> None:
        """
        Initialize command executor.

        Args:
            chat_history_manager: ChatHistoryManager instance for cancellation notices
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
            logger.info(f"[CANCEL] Sent SIGINT (Ctrl+C) to PTY {session.pty_session_id}")
            return True
        except Exception as sigint_error:
            logger.warning("[CANCEL] Failed to send SIGINT: %s", sigint_error)
            return False

    async def _log_cancellation_to_chat(self, session: AgentTerminalSession, reason: str) -> None:
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
                raw_data=session.get_cancellation_metadata(reason),
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
        from services.simple_pty import simple_pty_manager

        try:
            simple_pty_manager.close_session(pty_session_id)
            logger.info(f"[CANCEL] Forcefully closed PTY session {pty_session_id}")
            return True
        except Exception as sigkill_error:
            logger.error(f"[CANCEL] Failed to forcefully close PTY: {sigkill_error}")
            return False

    async def _finalize_cancellation(self, session: AgentTerminalSession, reason: str) -> bool:
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
            logger.info(f"[CANCEL] Cancelled running command task for " f"session {session.session_id}")

        # Log cancellation (Issue #281: uses extracted helper)
        await self._log_cancellation_to_chat(session, reason)

        logger.info(f"[CANCEL] ✅ Command cancellation complete for " f"session {session.session_id}")
        return True

    def _live_pty(self, session: AgentTerminalSession):
        """The session's PTY, recreated if stale (e.g. after a backend restart); None if unavailable."""
        if not session.pty_session_id:
            logger.warning("No PTY session ID available for writing")
            return None
        from services.simple_pty import simple_pty_manager

        pty = simple_pty_manager.get_session(session.pty_session_id)
        if pty and pty.is_alive():
            return pty
        logger.warning(
            f"[PTY_WRITE] PTY session {session.pty_session_id} not alive (exists={pty is not None}), recreating..."
        )
        new_pty = simple_pty_manager.create_session(session.pty_session_id, initial_cwd=str(PATH.PROJECT_ROOT))
        if not new_pty:
            logger.error(f"Failed to recreate PTY session {session.pty_session_id}")
            return None
        logger.info("Recreated PTY session %s", session.pty_session_id)
        return new_pty

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
        try:
            pty = self._live_pty(session)
            if pty is None:
                return False
            success = pty.write_input(text)
            if success:
                logger.debug("Wrote to PTY %s: %s...", session.pty_session_id, text[:50])
            return success
        except Exception as e:
            logger.error("Error writing to PTY: %s", e)
            return False

    async def cancel_command(self, session: AgentTerminalSession, reason: str = "timeout") -> bool:
        """
        Cancel a running command with graceful shutdown. Ref: #1088.

        Issue #665: Uses _send_sigint_to_pty, _force_close_pty_session, _finalize_cancellation.
        CRITICAL FIX (Critical #3): Prevents orphaned processes on timeout.
        """
        if not session.has_pty_session():
            logger.warning(f"[CANCEL] No PTY session to cancel for {session.session_id}")
            return False

        try:
            from services.simple_pty import simple_pty_manager

            pty = simple_pty_manager.get_session(session.pty_session_id)
            if not pty or not pty.is_alive():
                logger.info(f"[CANCEL] PTY session {session.pty_session_id} not alive, " f"nothing to cancel")
                return False

            logger.warning(f"[CANCEL] Cancelling command due to {reason}: " f"PTY {session.pty_session_id}")

            # Issue #281: Step 1 - Send SIGINT using extracted helper
            self._send_sigint_to_pty(session)

            # Step 2: Wait for graceful shutdown
            await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)

            # Step 3: Check if process is still running (Issue #665: uses helper)
            if pty.is_alive():
                logger.warning(
                    "[CANCEL] Process still running after SIGINT, " "attempting forceful termination (SIGKILL)"
                )
                if not self._force_close_pty_session(session.pty_session_id):
                    return False
            else:
                logger.info("[CANCEL] Process terminated gracefully after SIGINT")

            # Steps 4-5: Cleanup and finalize (Issue #665: extracted helper)
            return await self._finalize_cancellation(session, reason)

        except Exception as e:
            logger.error("[CANCEL] Error during command cancellation: %s", e, exc_info=True)
            return False

    async def _handle_poll_timeout(self, session: AgentTerminalSession, elapsed: float) -> None:
        """
        Cancel a command that outran its timeout (Issue #665: extracted helper).

        CRITICAL FIX (Critical #3): Cancels command to prevent orphaned processes.
        Nothing else is written to the PTY afterwards (#17074).
        """
        logger.warning(
            f"[PTY_EXEC] Polling timeout reached ({elapsed:.2f}s), " f"cancelling command to prevent orphaned processes"
        )
        if await self.cancel_command(session, reason="timeout"):
            logger.info("[PTY_EXEC] Successfully cancelled command after timeout")
        else:
            logger.error("[PTY_EXEC] Failed to cancel command after timeout - " "may have orphaned process")

    async def _await_exit_code(
        self, session: AgentTerminalSession, pty, start: int, marker: str, timeout: float
    ) -> tuple[int | None, bool]:
        """
        Watch the PTY transcript from *start* until the exit-code marker appears.

        SECURITY FIX (Critical #2): the marker is UUID-based, so a command cannot
        fake its exit code (`echo "EXIT_CODE:0" && malicious_command`). Each poll
        reads only output it has not scanned yet.

        Returns:
            (exit code, timed out). The code is None when the shell ended first,
            or when the command was cancelled on timeout; nothing is then read
            from a new shell.
        """
        deadline = time.monotonic() + timeout
        cursor, poll_interval = start, TimingConstants.MICRO_DELAY / 2
        while time.monotonic() < deadline:
            cursor, return_code = _scan_for_exit_code(pty, cursor, marker)
            if return_code is not None or not pty.is_alive():
                return return_code, False
            await asyncio.sleep(min(poll_interval, max(deadline - time.monotonic(), 0)))
            poll_interval = min(poll_interval * 1.5, 1.0)
        await asyncio.sleep(_READER_GRACE_S)
        _, return_code = _scan_for_exit_code(pty, cursor, marker)
        if return_code is not None:
            return return_code, False
        await self._handle_poll_timeout(session, timeout)
        return None, True

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

    def _build_pty_timeout_result(self, output: str, timeout: float) -> Metadata:
        """A command cancelled on timeout: never a success, and no exit code was read (#17074)."""
        return {
            "status": "timeout",
            "stdout": output,
            "stderr": f"Command timed out after {timeout:g}s and was cancelled",
            "return_code": TIMED_OUT_RETURN_CODE,
        }

    async def execute_in_pty(
        self, session: AgentTerminalSession, command: str, timeout: float | None = None
    ) -> Metadata:
        """
        Execute command directly in PTY shell (true collaboration mode).

        Args:
            session: Agent terminal session
            command: Command to execute
            timeout: Max seconds to wait (default: AUTOBOT_AGENT_COMMAND_TIMEOUT_S)

        Returns:
            Dict with status, stdout, stderr, return_code
        """
        timeout = AGENT_COMMAND_TIMEOUT_S if timeout is None else timeout
        logger.info("[PTY_EXEC] Executing in PTY: %s", command)

        marker = f"__EXIT_CODE_{uuid.uuid4()}__:"
        try:
            pty = self._live_pty(session)
        except Exception as e:
            logger.error("Error preparing PTY: %s", e)
            pty = None
        start = pty.transcript_position() if pty else 0
        if pty is None or not pty.write_input(f"{command}\necho '{marker}'$?\n"):
            return self._build_pty_error_result("Failed to write command to PTY")

        return_code, timed_out = await self._await_exit_code(session, pty, start, marker, timeout)
        output = _output_since(pty, start, command, marker)
        if timed_out:
            return self._build_pty_timeout_result(output, timeout)
        if return_code is None:
            return {
                **self._build_pty_error_result("The shell ended before the command reported an exit code"),
                "stdout": output,
            }
        logger.info(f"[PTY_EXEC] Command complete. Return code: {return_code}, output: {len(output)} chars")
        return self._build_pty_result(output, return_code)
