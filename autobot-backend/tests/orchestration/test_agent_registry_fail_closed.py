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
    is_unbounded_agent_id,
    resolve_agent_id,
    resolve_forbidden_tools,
)

# ------------------------------------------------------------ the fail-open fix


def test_an_unknown_agent_id_is_bounded_not_unleashed():
    """The defect, directly: an unrecognised id must not mean "nothing forbidden"."""
    forbidden = resolve_forbidden_tools("no_such_agent")

    assert forbidden, "an unknown agent id resolved to no boundary at all"
    assert forbidden == DEFAULT_FORBIDDEN_TOOLS


def test_the_default_is_stricter_than_any_profile_not_merely_equal_to_them():
    """The property that makes falling closed worth the name.

    A misidentified agent must not land on the *typical* profile boundary: that set
    is only infra/shell, so it would still leave ``terminal``, ``write_file``,
    ``delete_file``, ``git_force_push`` and ``code_interpreter`` reachable. The
    default has to dominate every real profile's manifest, strictly.
    """
    profile_manifests = [frozenset(p.forbidden_work) for p in get_default_agents() if p.forbidden_work]

    assert profile_manifests, "no bounded profiles — this test would pass vacuously"
    for manifest in profile_manifests:
        assert manifest < DEFAULT_FORBIDDEN_TOOLS, "the default is no stricter than a profile"


@pytest.mark.parametrize("tool", ["terminal", "write_file", "delete_file", "git_force_push", "code_interpreter"])
def test_the_default_covers_what_the_profile_default_leaves_open(tool):
    """Named explicitly: these are the tools an unknown id reached under INFRA_AND_SHELL."""
    assert tool not in set(INFRA_AND_SHELL_TOOLS)
    assert tool in DEFAULT_FORBIDDEN_TOOLS


def test_no_agent_id_stays_unbounded():
    """The plain chat agent has no identity to bound — the documented exception."""
    assert resolve_forbidden_tools(None) == frozenset()
    assert resolve_forbidden_tools("") == frozenset()


def test_a_registered_bounded_agent_keeps_its_declared_manifest():
    """Reads the profile — it does not just hand back the fallback.

    Only discriminating because the default is now strictly wider than any profile
    manifest: delete the profile lookup and this fails, where against an equal
    default it would have passed either way.
    """
    resolved = resolve_forbidden_tools("research_agent")

    assert resolved == frozenset(INFRA_AND_SHELL_TOOLS)
    assert resolved != DEFAULT_FORBIDDEN_TOOLS


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

    assert not [r for r in caplog.records if "research_agent" in r.getMessage()]
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

    Asserted per-id against the *expected source* of the manifest, not merely
    "non-empty": an id with a profile must get that profile's manifest, and one
    without must get the fallback. A blanket truthiness check would pass even if the
    profile lookup were deleted, since both answers are non-empty.
    """
    from api.agent_config import DEFAULT_AGENT_CONFIGS

    mismatched = {}
    for agent_id in DEFAULT_AGENT_CONFIGS:
        resolved = resolve_agent_id(agent_id)
        if resolved is not None and is_unbounded_agent_id(agent_id):
            expected = frozenset()
        elif resolved is not None:
            expected = frozenset(next(p for p in get_default_agents() if p.agent_id == resolved).forbidden_work)
        else:
            expected = DEFAULT_FORBIDDEN_TOOLS
        actual = resolve_forbidden_tools(agent_id)
        if actual != expected:
            mismatched[agent_id] = (sorted(expected), sorted(actual))

    assert mismatched == {}, f"DB-namespace ids resolving to the wrong manifest: {mismatched}"


def test_the_db_namespace_check_is_not_vacuous():
    """Both branches of the test above must actually occur, or it proves little."""
    from api.agent_config import DEFAULT_AGENT_CONFIGS

    with_profile = [a for a in DEFAULT_AGENT_CONFIGS if resolve_agent_id(a) is not None]
    without_profile = [a for a in DEFAULT_AGENT_CONFIGS if resolve_agent_id(a) is None]

    assert with_profile, "no DB id resolved to a profile"
    assert without_profile, "every DB id resolved — the fallback branch is never exercised"


# ------------------------------------------------- executors are not delegable


def test_an_executor_is_recognised_as_unbounded():
    assert is_unbounded_agent_id("system_agent") is True
    assert is_unbounded_agent_id("system_commands") is True


@pytest.mark.parametrize("agent_id", ["research_agent", "no_such_agent", None, ""])
def test_everything_else_is_not_unbounded(agent_id):
    """An id nobody recognises is bounded, not an executor — the two must not merge."""
    assert is_unbounded_agent_id(agent_id) is False


@pytest.mark.asyncio
async def test_delegation_refuses_an_executor_agent_type():
    """A bounded agent must not obtain an unbounded subagent by naming one.

    ``agent_type`` arrives straight from the model's tool call and ``delegate`` is not
    itself an infra/shell tool, so a parent with a manifest can still call it. Without
    this refusal the subagent's boundary is whatever the parent asked for.
    """
    from chat_workflow.delegation import run_delegated_subtask

    with pytest.raises(ValueError, match="unbounded"):
        await run_delegated_subtask("do a thing", agent_type="system_agent")


@pytest.mark.asyncio
async def test_delegation_still_accepts_an_unregistered_agent_type(monkeypatch):
    """Unknown ids are already safe — they resolve to the default boundary.

    Refusing them too would turn a typo into a hard failure for no security gain, so
    the check is narrowly about executors.
    """
    from chat_workflow import delegation

    seen = {}

    async def _fake_engine(task, agent_type, depth):
        seen.update(task=task, agent_type=agent_type, depth=depth)
        return "ok"

    monkeypatch.setitem(delegation._ENGINES, "claude_code", _fake_engine)

    assert await delegation.run_delegated_subtask("t", agent_type="typo_agent") == "ok"

    assert seen["agent_type"] == "typo_agent"
