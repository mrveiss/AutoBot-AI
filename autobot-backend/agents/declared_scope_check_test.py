# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A malformed declared scope is refused by name on the agent path too (#16209 AC4).

Before this, `BaseAgent.execute_with_tracking` passed the declaration straight to
`hold_scopes`, and the `ScopeError` from `Scope.parse` escaped as an exception.
"""

from typing import List

import pytest

from agents.base_agent import LocalAgent
from agents.base_agent_types import AgentRequest, AgentResponse
from agents.declared_scope_check import INVALID_DECLARED_SCOPE, malformed_scope_response

#: Every rejection the scope grammar makes, as in tests/coordination/test_work_claims.py.
_REJECTED = ["nokind", "bogus:a/b", "path:", "path:a//b", "path:a/../b", "path:a/./b", "path:a/b c"]


def _request() -> AgentRequest:
    return AgentRequest(request_id="req-1", agent_type="scoped", action="write", payload={})


class _ScopedAgent(LocalAgent):
    """Declares whatever scopes the test hands it, and records whether it ever ran."""

    def __init__(self, scopes: List[str]) -> None:
        super().__init__("scoped")
        self._scopes = scopes
        self.ran = False

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        self.ran = True
        return AgentResponse(request_id=request.request_id, agent_type=self.agent_type, status="success", result={})

    def get_capabilities(self) -> List[str]:
        return ["write"]

    def declared_scopes(self, request: AgentRequest) -> List[str]:
        return list(self._scopes)


@pytest.mark.parametrize("raw", _REJECTED)
def test_every_rejected_scope_gets_a_refusal_that_names_it(raw):
    response = malformed_scope_response(_request(), ["path:ok", raw], agent_type="scoped")
    assert response is not None and response.status == "error"
    assert response.error.startswith(INVALID_DECLARED_SCOPE)
    assert response.metadata["invalid_scope"] == raw, "the refusal must say which declaration was wrong"


@pytest.mark.parametrize("scopes", [[], ["path:a"], ["path:a/b", "path:c"]])
def test_valid_declarations_are_not_refused(scopes):
    """The contrast: the check must not become "refuse everything"."""
    assert malformed_scope_response(_request(), scopes, agent_type="scoped") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", _REJECTED)
async def test_execute_with_tracking_refuses_by_name_instead_of_raising(raw):
    agent = _ScopedAgent([raw])
    response = await agent.execute_with_tracking(_request())
    assert response.status == "error" and response.error.startswith(INVALID_DECLARED_SCOPE), response
    assert not agent.ran, "a refused run must never reach process_request"
    assert agent.error_count == 1
