# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""#14811: a skipped manager must not leave its subordinates pointing at nothing.

`execute_import` pre-mints a destination UUID for **every** agent in the template
before any INSERT, so `reports_to` could be remapped without depending on the
order agents appear in. `_import_agent` then decides — per agent — whether the
row is actually created: a name already used in the target company, an adapter
that cannot run on this host (#14800), or a duplicate name inside the template
itself all return None.

Pass 1 therefore *predicts* the insert set and pass 2 *decides* it, and nothing
reconciled the two. A subordinate whose manager was skipped was written with the
manager's pre-minted UUID — an id belonging to a row that was never inserted.
There is no foreign key on `reports_to`, so nothing rejected it, at import time
or ever.

The consequence is not cosmetic. `/api/agents`' org tree roots on
`reports_to IS NULL` and matches children by `agent_id`, so an agent referencing
a nonexistent manager is neither a root nor anyone's child: it disappears from
the tree entirely, cannot be delegated to, and cannot escalate — while the
import reports success and the LLC org chart still renders it, because that
endpoint promotes an unresolvable parent to a root.

These pin the invariant: a reporting line is attached only when the manager
actually landed, and one that cannot be honoured is **named in the result**
rather than written as a pointer to nothing.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from llc.services.portability import PortabilityService


class _FakeSession:
    """Captures executed statements; enough of AsyncSession for execute_import."""

    def __init__(self) -> None:
        self.statements: List[Any] = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: None))

    async def begin_nested(self):
        return SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


def _updates(session: _FakeSession) -> Dict[str, str]:
    """agent_id -> reports_to, for every UPDATE the linker issued."""
    out: Dict[str, str] = {}
    for stmt in session.statements:
        if "UPDATE agent_org_nodes SET reports_to" not in str(stmt):
            continue
        params = stmt.compile().params
        out[params["aid"]] = params["mgr"]
    return out


def _agent(agent_id: str, name: str, reports_to: str | None = None) -> Dict[str, Any]:
    return {"agent_id": agent_id, "name": name, "reports_to": reports_to}


class TestALandedManagerGetsItsReportingLine:
    @pytest.mark.asyncio
    async def test_the_line_uses_the_destination_id_not_the_source_id(self):
        """The remap still has to happen — it just has to happen against reality."""
        session = _FakeSession()
        svc = PortabilityService(session)
        agents = [_agent("src-mgr", "CEO"), _agent("src-sub", "Engineer", reports_to="src-mgr")]
        landed = {"src-mgr": "dst-mgr", "src-sub": "dst-sub"}
        dropped: List[Dict[str, str]] = []

        await svc._link_reporting_lines(agents, landed, dropped)

        assert _updates(session) == {"dst-sub": "dst-mgr"}
        assert dropped == []


class TestASkippedManagerLeavesNoDanglingPointer:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("reason", ["name-already-exists", "adapter-cannot-run"])
    async def test_the_subordinate_is_left_a_root_and_the_loss_is_named(self, reason):
        """Both skip routes reach this code the same way — by the manager's absence.

        Parametrised on the reason to document that the linker does not know or
        care which gate declined the manager; what matters is that it is not in
        `landed`.
        """
        session = _FakeSession()
        svc = PortabilityService(session)
        agents = [_agent("src-mgr", "CEO"), _agent("src-sub", "Engineer", reports_to="src-mgr")]
        landed = {"src-sub": "dst-sub"}  # the manager did not land, for `reason`
        dropped: List[Dict[str, str]] = []

        await svc._link_reporting_lines(agents, landed, dropped)

        assert _updates(session) == {}, "no UPDATE may name a manager that was never inserted"
        assert dropped == [
            {
                "agent_name": "Engineer",
                "agent_id": "dst-sub",
                "manager_name": "CEO",
                "manager_source_agent_id": "src-mgr",
            }
        ]

    @pytest.mark.asyncio
    async def test_a_manager_absent_from_the_template_entirely_is_also_reported(self):
        """A hand-authored template can name an id that was never in the file."""
        session = _FakeSession()
        svc = PortabilityService(session)
        agents = [_agent("src-sub", "Engineer", reports_to="never-existed")]
        dropped: List[Dict[str, str]] = []

        await svc._link_reporting_lines(agents, {"src-sub": "dst-sub"}, dropped)

        assert _updates(session) == {}
        assert len(dropped) == 1
        assert dropped[0]["manager_source_agent_id"] == "never-existed"
        assert dropped[0]["manager_name"] == "", "no name is knowable for an id not in the template"

    @pytest.mark.asyncio
    async def test_a_skipped_subordinate_is_not_reported_as_a_dropped_line(self):
        """It has no reporting line to lose — it was never created."""
        session = _FakeSession()
        svc = PortabilityService(session)
        agents = [_agent("src-mgr", "CEO"), _agent("src-sub", "Engineer", reports_to="src-mgr")]
        dropped: List[Dict[str, str]] = []

        await svc._link_reporting_lines(agents, {"src-mgr": "dst-mgr"}, dropped)

        assert _updates(session) == {}
        assert dropped == []


class TestNothingIsLostWhenNothingIsSkipped:
    @pytest.mark.asyncio
    async def test_every_declared_reporting_line_survives_a_clean_import(self):
        """The no-data-loss invariant, asserted rather than assumed."""
        session = _FakeSession()
        svc = PortabilityService(session)
        agents = [
            _agent("a", "CEO"),
            _agent("b", "VP", reports_to="a"),
            _agent("c", "Engineer", reports_to="b"),
            _agent("d", "Engineer II", reports_to="b"),
        ]
        landed = {"a": "A", "b": "B", "c": "C", "d": "D"}
        dropped: List[Dict[str, str]] = []

        await svc._link_reporting_lines(agents, landed, dropped)

        assert _updates(session) == {"B": "A", "C": "B", "D": "B"}
        assert dropped == []
        declared = sum(1 for a in agents if a["reports_to"])
        assert len(_updates(session)) + len(dropped) == declared, "every declared line is either attached or reported"


class TestTheImportActuallyRunsPassThree:
    """The wiring, not just the helper.

    A correct `_link_reporting_lines` that `execute_import` never calls would
    leave every imported agent a root and every one of the tests above green.
    """

    @pytest.mark.asyncio
    async def test_execute_import_links_landed_agents_and_reports_the_rest(self):
        session = _FakeSession()
        svc = PortabilityService(session)
        template = {
            "agents": [_agent("src-mgr", "CEO"), _agent("src-sub", "Engineer", reports_to="src-mgr")],
        }
        company_id = uuid.uuid4()

        async def _import_agent(agent, *a, **kw):
            # The manager is skipped; the subordinate lands.
            return None if agent["name"] == "CEO" else "dst-sub"

        with (
            patch.object(PortabilityService, "_validate_schema", return_value=None),
            patch.object(PortabilityService, "_resolve_or_create_company", AsyncMock(return_value=company_id)),
            patch.object(PortabilityService, "_import_agent", side_effect=_import_agent),
        ):
            result = await svc.execute_import(template)

        assert result["skipped"]["agents"] == ["CEO"]
        assert _updates(session) == {}, "pass 3 must not link a manager that was skipped"
        assert result["dropped_reporting_lines"] == [
            {
                "agent_name": "Engineer",
                "agent_id": "dst-sub",
                "manager_name": "CEO",
                "manager_source_agent_id": "src-mgr",
            }
        ], "the lost reporting line must reach the caller, not only the log"
