# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The service's half of interpretation ownership (#13480, #21202).

``interpretation_turn`` holds the compare-and-set key; these methods bind it to the service's Redis so the
polling chat turn and the worker that ran the command reach the same key.
"""

from __future__ import annotations

import uuid

from autobot_shared.logging_manager import get_logger

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
