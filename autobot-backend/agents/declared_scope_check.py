# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Refuse a declared work scope the claim grammar rejects, by name (#16209).

`hold_scopes` hands each declared scope to `Scope.parse`. A `ScopeError` from
there is not `ClaimUnavailable`, so it escapes the context manager, and out of
`BaseAgent.execute_with_tracking` as an exception. The a2a executor already
fails such a task with the value named; this gives an agent's caller the same
answer -- which value, and why -- instead of a traceback.

Kept apart from `scope_enforcement` so neither module grows past its size
budget; `base_agent` imports it the way it imports `refused_response`.
"""

from __future__ import annotations

from typing import Sequence

from agents.base_agent_types import AgentRequest, AgentResponse
from autobot_shared.coordination import Scope, ScopeError
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

INVALID_DECLARED_SCOPE = "invalid_declared_scope"


def malformed_scope_response(request: AgentRequest, scopes: Sequence[str], *, agent_type: str) -> AgentResponse | None:
    """An error response naming the first scope the grammar rejects; None when every scope parses."""
    for raw in scopes:
        try:
            Scope.parse(raw)
        except ScopeError as exc:
            logger.info("Agent %s refused a malformed declared scope %r: %s", agent_type, raw, exc)
            return AgentResponse(
                request_id=request.request_id,
                agent_type=agent_type,
                status="error",
                result=None,
                error=f"{INVALID_DECLARED_SCOPE}: {exc}",
                metadata={"declared_scopes": list(scopes), "invalid_scope": raw, "reason": str(exc)},
            )
    return None
