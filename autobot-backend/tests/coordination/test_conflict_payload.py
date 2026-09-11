# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One wire shape for a refusal, whichever layer reports it (#16208).

Three sites rendered one ``ClaimConflict`` in three shapes: two flat, one
nested, with the scope named ``refused_scope`` in two and ``requested`` in the
third. The presence panel (#15951) would have had to parse all three. These pin
the single shape, its holder, and every site that writes it.
"""

from dataclasses import fields
from types import SimpleNamespace

import pytest

from autobot_shared.coordination.work_claims import Claim, ClaimConflict, claim_payload, conflict_payload
from services import claim_projection

_HOLDER = Claim(
    scope="path:a/b.py",
    agent_id="agent-9",
    task_id="t9",
    mode="exclusive",
    intent="fix the header parse",
    acquired_at="2026-01-01T00:00:00Z",
    expires_at="2026-01-01T00:05:00Z",
)


@pytest.mark.asyncio
async def test_a_refusal_holder_is_the_claims_table_row_for_that_claim(monkeypatch):
    """A client parses a holder once: it IS the row `GET /api/coordination/claims` returns."""

    async def _list_claims(_kind=None):
        return [_HOLDER]

    monkeypatch.setattr(claim_projection, "list_claims", _list_claims)
    conflict = ClaimConflict(requested="path:a/b.py", holder=_HOLDER)

    assert conflict_payload(conflict)["holder"] == (await claim_projection.claim_table())[0]


def test_every_field_of_a_conflict_and_its_holder_reaches_the_payload():
    """A field added to either dataclass later cannot be dropped by a projection nobody updated."""
    holder = Claim(**{f.name: f"value-of-{f.name}" for f in fields(Claim)} | {"scope": "path:a/b.py"})
    conflict = ClaimConflict(requested="path:a/c.py", holder=holder)
    payload = conflict_payload(conflict)

    for f in fields(ClaimConflict):
        expected = claim_payload(holder) if f.name == "holder" else getattr(conflict, f.name)
        assert payload[f.name] == expected, f"ClaimConflict.{f.name} did not reach the payload"
    for f in fields(Claim):
        assert payload["holder"][f.name] == getattr(holder, f.name), f"Claim.{f.name} did not reach the holder"


@pytest.mark.asyncio
async def test_every_layer_that_reports_a_refusal_writes_the_same_shape(monkeypatch):
    """The agent response, the A2A artifact and the event carry one shape; the event only adds who asked."""
    from a2a.task_executor import _report_refusal
    from agents.scope_enforcement import refused_response

    conflict = ClaimConflict(requested="path:a/b.py", holder=_HOLDER)
    expected = conflict_payload(conflict)

    response = refused_response(SimpleNamespace(request_id="r1"), conflict, agent_type="writer")

    artifacts: list = []
    manager = SimpleNamespace(
        add_artifact=lambda _task_id, artifact: artifacts.append(artifact),
        update_state=lambda *_a, **_k: None,
        publish_event=lambda *_a, **_k: None,
    )
    _report_refusal(manager, "t2", conflict)

    events: list = []

    async def _publish(_channel, _event_type, payload, **_kwargs):
        events.append(payload)

    monkeypatch.setattr(claim_projection, "publish_event", _publish)
    await claim_projection.publish_conflict(conflict, agent_id="agent-2", task_id="t2")

    assert response.metadata == expected
    assert artifacts[0].content == expected
    assert {k: v for k, v in events[0].items() if k not in ("agent_id", "task_id")} == expected
