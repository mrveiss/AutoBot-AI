# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``resolve_forbidden_tools`` fails closed on an unrecognised agent id (GH#13588).

The defect: an id the registry did not recognise resolved to an *empty* manifest,
which the enforcement seams read as "nothing is forbidden". A typo, or an id from
AutoBot's other agent-id namespace, therefore produced a silently unbounded agent —
identical in effect to naming the designated executor.

What makes it reachable is that the two producers of an agent id disagree about
validation: ``session_role.set_role`` (server-side, trusted) *rejects* an id outside
this registry, while a client-supplied ``context["agent_id"]`` and the ``delegate``
tool's LLM-chosen ``agent_type`` are passed through unchecked. The validated path
refused exactly the strings the unvalidated ones rewarded with no boundary.
"""

import pytest

from autobot_shared.tool_catalogue import INFRA_AND_SHELL_TOOLS
from orchestration.agent_registry import (
    DEFAULT_FORBIDDEN_TOOLS,
    agent_type_aliases,
    get_default_agents,
    resolve_agent_id,
    resolve_forbidden_tools,
)


# ------------------------------------------------------------ the fail-open fix


def test_an_unknown_agent_id_is_bounded_not_unleashed():
    """The defect, directly: an unrecognised id must not mean "nothing forbidden"."""
    forbidden = resolve_forbidden_tools("no_such_agent")

    assert forbidden, "an unknown agent id resolved to no boundary at all"
    assert forbidden == DEFAULT_FORBIDDEN_TOOLS


def test_the_default_boundary_covers_the_tools_the_boundary_exists_for():
    """Falling closed is only meaningful if it lands on the infra/shell set."""
    assert set(INFRA_AND_SHELL_TOOLS) <= DEFAULT_FORBIDDEN_TOOLS


def test_no_agent_id_stays_unbounded():
    """The plain chat agent has no identity to bound — the documented exception."""
    assert resolve_forbidden_tools(None) == frozenset()
    assert resolve_forbidden_tools("") == frozenset()


def test_a_registered_bounded_agent_keeps_its_declared_manifest():
    assert resolve_forbidden_tools("research_agent") == frozenset(INFRA_AND_SHELL_TOOLS)


@pytest.mark.parametrize("executor", ["system_agent", "system_commands"])
def test_a_declared_executor_is_still_unbounded(executor):
    """Failing closed must not bound the agents whose job is infra/shell."""
    assert resolve_forbidden_tools(executor) == frozenset()


def test_the_warning_names_the_id_that_missed(caplog):
    """An unresolved id has to be observable, or the miss is only found in an audit."""
    with caplog.at_level("WARNING"):
        resolve_forbidden_tools("typo_agent")

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "typo_agent" in logged
    assert "GH#13588" in logged


def test_a_resolved_id_logs_nothing(caplog):
    with caplog.at_level("WARNING"):
        resolve_forbidden_tools("research_agent")

    assert "GH#13588" not in "\n".join(r.getMessage() for r in caplog.records)


# ------------------------------------------------- "unbounded" is declared, not inferred


def test_every_profile_is_bounded_or_says_it_is_not():
    """A forgotten ``forbidden_work`` must not read as a deliberate executor grant.

    This is the property that keeps the fix from decaying: add a profile, forget its
    manifest, and this fails rather than shipping another silently unbounded agent.
    """
    undeclared = [p.agent_id for p in get_default_agents() if not p.forbidden_work and not p.unbounded]

    assert undeclared == [], f"profiles with no boundary and no `unbounded=True`: {undeclared}"


def test_only_the_designated_executors_declare_themselves_unbounded():
    unbounded = sorted(p.agent_id for p in get_default_agents() if p.unbounded)

    assert unbounded == ["system_agent", "system_commands"]


# ------------------------------------------------------------ namespace reconciliation


def test_agent_type_reconciles_the_two_naming_styles():
    """The DB namespace's ``research`` is this registry's ``research_agent``."""
    assert resolve_agent_id("research") == "research_agent"
    assert resolve_agent_id("orchestrator") == "coordination_agent"


def test_an_ambiguous_agent_type_resolves_to_nothing():
    """``librarian`` names two profiles; guessing one of them would be a coin flip."""
    assert "librarian" not in agent_type_aliases()
    assert resolve_agent_id("librarian") is None


def test_an_executor_is_not_reachable_through_its_agent_type():
    """Aliasing must never hand out a boundary-free manifest.

    ``system_agent``'s ``agent_type`` is ``system_commands`` and ``system_commands``'
    is ``executor``. If aliases included unbounded profiles, the string ``executor`` —
    which names no agent anyone configured — would resolve to a full infra/shell
    grant, re-creating this issue's escalation with an extra step.
    """
    assert "executor" not in agent_type_aliases()
    assert resolve_forbidden_tools("executor") == DEFAULT_FORBIDDEN_TOOLS


def test_every_db_namespace_agent_id_is_bounded():
    """AC: an id from the DB seed is bounded exactly as its profile counterpart is.

    ``api/agent_config.py`` seeds 29 agent ids; only a handful share a name with a
    capability profile. Before this fix the other ~22 resolved to no boundary at all.
    """
    from api.agent_config import DEFAULT_AGENT_CONFIGS

    unbounded_ids = sorted(p.agent_id for p in get_default_agents() if p.unbounded)
    unexpected = sorted(
        agent_id
        for agent_id in DEFAULT_AGENT_CONFIGS
        if agent_id not in unbounded_ids and not resolve_forbidden_tools(agent_id)
    )

    assert unexpected == [], f"DB-namespace agent ids with no tool boundary: {unexpected}"
