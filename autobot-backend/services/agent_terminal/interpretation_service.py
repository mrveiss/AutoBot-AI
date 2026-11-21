# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The service's half of interpretation ownership (#13480, #21202).

``interpretation_turn`` holds the compare-and-set key; these methods bind it to the service's Redis so the
polling chat turn and the worker that ran the command reach the same key.
"""

from __future__ import annotations

import copy
import uuid

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.logging_manager import get_logger
from type_defs.common import Metadata

from .interpretation_turn import register_turn, release_turn, take_for_command, take_for_turn
from .models import AgentTerminalSession
from .session_state import ApprovalStateUnavailableError, pending_decision_id

logger = get_logger(__name__)


class InterpretationOwnershipMixin:
    """Needs ``self.session_manager`` (its ``redis_client`` is the shared store)."""

    async def begin_interpreting_turn(self, session_id: str, command_id: str | None) -> str:
        """Register a polling chat turn as the interpreter of this session's approval; returns its token (#21202).

        The ownership is one compare-and-set key in Redis (``interpretation_turn``), so the worker that runs the
        approved command sees it whichever worker the turn polls on.
        """
        token = uuid.uuid4().hex
        await register_turn(self.session_manager.redis_client, session_id, command_id, token)
        return token

    async def take_turn_interpretation(self, session_id: str, command_id: str | None, token: str) -> bool:
        """The turn has the result: ``True`` if it owns the interpretation, ``False`` if the command worker did."""
        return await take_for_turn(self.session_manager.redis_client, session_id, command_id, token)

    async def end_interpreting_turn(self, session_id: str, command_id: str | None, token: str) -> None:
        """The turn is leaving: give up its token so the command's worker interprets (#21202)."""
        await release_turn(self.session_manager.redis_client, session_id, command_id, token)

    async def _owns_interpretation(self, session: AgentTerminalSession) -> bool:
        """Whether this worker interprets the result. Without a Redis to settle it, it does: a duplicate beats none."""
        try:
            return await take_for_command(
                self.session_manager.redis_client, session.session_id, pending_decision_id(session.pending_approval)
            )
        except ApprovalStateUnavailableError as exc:
            logger.error(
                "Interpretation ownership of session %s unconfirmed, interpreting here: %s", session.session_id, exc
            )
            return True

    def _interpret_in_background(self, session: AgentTerminalSession, command: str, result: Metadata) -> None:
        """Interpret an approved command's result AFTER the approve request has answered (#19951).

        The interpretation is an LLM call; awaiting it inside the approve request left the button looking dead for
        seconds. The task works on a snapshot of the session: ownership of the interpretation is keyed by the
        pending approval's decision id, which ``settle_pending`` clears moments after this is scheduled.
        ``_interpret_approved_command`` logs its own failure, and ``fire_and_forget`` logs anything it misses.
        """
        fire_and_forget(
            self._interpret_approved_command(copy.copy(session), command, result),
            name=f"interpret-approved-{session.session_id}",
        )

    def _interpret_command_result(self, session: AgentTerminalSession, command: str, result: Metadata) -> None:
        """Schedule the LLM interpretation of an auto-approved command; the tool result never waits on it (#21938).

        The interpretation is auxiliary: a slow or failing model must not hold the command's result or fail the
        turn. It runs as a background task like the approve path's (``_interpret_in_background``).
        """
        if session.has_conversation() and self.chat_workflow_manager:
            fire_and_forget(
                self._run_auto_interpretation(session.conversation_id, command, result),
                name=f"interpret-auto-{session.session_id}",
            )

    async def _run_auto_interpretation(self, conversation_id: str, command: str, result: Metadata) -> None:
        """The background half: a failure is logged here and goes no further (#21938)."""
        try:
            logger.info("[INTERPRETATION] Starting LLM interpretation for command: %s", command)
            await self.chat_workflow_manager.interpret_terminal_command(
                command=command,
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                return_code=result.get("return_code", 0),
                session_id=conversation_id,
            )
        except Exception as exc:  # noqa: BLE001 - auxiliary step; the command already succeeded
            logger.error("[INTERPRETATION] Failed to interpret results: %s", exc)
