# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat turn's half of interpretation ownership (#13480, #21202).

The ownership key and its compare-and-set live in ``services.agent_terminal.interpretation_turn``; the polling
turn reaches them through the agent terminal service. A turn that cannot register interprets alone.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Set on a finished command's result when the worker that ran it already took its interpretation (#21202).
INTERPRETED_ELSEWHERE = "interpretation_owned_elsewhere"


class InterpretationTurnMixin:
    """Register, settle and release a polling turn's claim on interpreting an approved command's result."""

    def _terminal_service(self):
        """The agent terminal service, if this handler has one that can coordinate interpretation."""
        service = getattr(self.terminal_tool, "agent_terminal_service", None)
        return service if hasattr(service, "begin_interpreting_turn") else None

    async def _begin_interpretation_turn(self, terminal_session_id: str, command_id: str | None) -> str | None:
        """Register this turn as the interpreter (#21202); ``None`` if it could not, so the turn interprets alone."""
        service = self._terminal_service()
        if service is None:
            return None
        try:
            return await service.begin_interpreting_turn(terminal_session_id, command_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not register as the interpreting turn of %s: %s", terminal_session_id, exc)
            return None

    async def _settle_interpretation(
        self, terminal_session_id: str, command_id: str | None, token: str | None, result: dict | None
    ) -> None:
        """Take the interpretation of a finished command, or mark the result as interpreted elsewhere (#21202)."""
        service = self._terminal_service()
        if service is None or token is None or not result or result.get("status") != "success":
            return
        try:
            owned = await service.take_turn_interpretation(terminal_session_id, command_id, token)
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not settle interpretation of %s, interpreting here: %s", terminal_session_id, exc)
            return
        if not owned:
            result[INTERPRETED_ELSEWHERE] = True

    async def _end_interpretation_turn(
        self, terminal_session_id: str, command_id: str | None, token: str | None
    ) -> None:
        """Release this turn's token (#21202). A failed release is logged; the key's TTL frees it."""
        service = self._terminal_service()
        if service is None or token is None:
            return
        try:
            await service.end_interpreting_turn(terminal_session_id, command_id, token)
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not release the interpreting turn of %s: %s", terminal_session_id, exc)

    async def _interpret_unless_elsewhere(self, approval_result: dict[str, Any], *args, **kwargs):
        """Stream the interpretation unless the command's worker took it (#21202): one interpretation per result."""
        if approval_result.get(INTERPRETED_ELSEWHERE):
            logger.info("[#21202] Result already interpreted by the worker that ran the command")
            return
        async for chunk in self._interpret_command_results(*args, **kwargs):
            yield chunk
