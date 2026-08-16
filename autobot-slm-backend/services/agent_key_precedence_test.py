# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM's own key must outrank the node's cached copy (#14350).

The agent authenticates its heartbeat against the SLM backend, which loads
``/etc/autobot/slm-secrets.env``. That file is the only source of truth for what
the agent's key must equal.

Two earlier orderings were each wrong in a different direction:

* the ``autobot_internal_api_key`` var carries the *managed backend's* key,
  which drifted from the SLM's on some installs — #11507 / #11450.
* the *node's* own copy is a cache from enrollment. When it goes stale, every
  redeploy faithfully rewrites the stale value and the manager cannot correct
  it. Observed live: an agent 401ing every 30 seconds, indefinitely, on a node
  that was otherwise fully current. The repair mechanism was reading its input
  from the thing that needed repairing.

This checks the resolution order in the role, which is a Jinja expression rather
than Python — so the rules parse the YAML and assert on the expression's
structure, not on prose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ROLE = Path(__file__).resolve().parent.parent / "ansible" / "roles" / "slm_agent" / "tasks" / "main.yml"
_TASKS = yaml.safe_load(_ROLE.read_text(encoding="utf-8"))

# The three sources, in the order they must be consulted.
_SLM_OWN = "_slm_own_key"
_NODE_FILE = "_agent_key_from_node"
_DEPLOY_VAR = "autobot_internal_api_key"


def _resolution_expression() -> str:
    """The Jinja that picks the effective key."""
    for task in _TASKS:
        if not isinstance(task, dict):
            continue
        fact = task.get("ansible.builtin.set_fact") or task.get("set_fact") or {}
        if "_agent_internal_api_key" in fact:
            return str(fact["_agent_internal_api_key"])
    raise AssertionError("no task sets _agent_internal_api_key — this rule is pinned to the wrong name")


def test_the_role_parses_and_the_expression_exists():
    """An unparseable role or a renamed fact would make every rule below vacuous."""
    assert _TASKS, "the role file parsed to nothing"
    assert _resolution_expression(), "the resolution expression is empty"


def test_all_three_sources_are_still_consulted():
    """Narrowing to one source would be a different bug, not a fix.

    A control node that cannot read its own key must still fall through to the
    node file rather than writing an empty key — an empty key 401s exactly like
    a stale one, with less to go on.
    """
    expression = _resolution_expression()

    for source in (_SLM_OWN, _NODE_FILE, _DEPLOY_VAR):
        assert source in expression, f"{source} dropped from the resolution order"


@pytest.mark.parametrize(
    "higher,lower",
    [
        (_SLM_OWN, _NODE_FILE),
        (_SLM_OWN, _DEPLOY_VAR),
        (_NODE_FILE, _DEPLOY_VAR),
    ],
)
def test_the_precedence_order_holds(higher, lower):
    """Position in the `or` chain is the precedence.

    Asserted pairwise rather than as one fixed string so a reformat, a line
    break, or an added source cannot make this pass by accident while the order
    silently changes.
    """
    expression = _resolution_expression()

    assert expression.index(higher) < expression.index(
        lower
    ), f"{lower} is consulted before {higher} — a stale or drifted key would win (#14350)"


def test_the_slm_key_is_read_from_the_control_node():
    """It must be delegated, or it reads the *target* node's file again.

    Without `delegate_to: localhost` this task would read the same stale copy
    the node file rule already covers, and the fix would be a no-op that looks
    like a fix.
    """
    task = next(
        (t for t in _TASKS if isinstance(t, dict) and "#14350" in str(t.get("name", ""))),
        None,
    )
    assert task is not None, "the authoritative-key task is gone"
    assert (
        task.get("delegate_to") == "localhost"
    ), "the SLM key task is not delegated, so it reads the target node rather than the SLM"
    assert task.get("failed_when") is False, "a control node without the file must fall through, not fail the deploy"
    assert task.get("no_log") is True, "the key task must not log its value"


def test_the_secret_is_never_exposed():
    """`no_log` where the VALUE could leak — not merely where the name appears.

    CI caught the first version of this rule demanding `no_log` on the
    "Warn when no internal API key could be resolved" task. That task is a
    `debug` gated on `when: not (_agent_internal_api_key | trim)` whose message
    contains the hostname and no key at all — it fires precisely when there is
    nothing to leak.

    Silencing it would have suppressed the only signal an operator gets that no
    key was resolved, to protect a value that is empty by definition. A guard
    that hides a diagnostic is worse than no guard.

    So: `when:` is a test, not an exposure. Strip it, then require `no_log` only
    where the key reaches a module argument.
    """
    for task in _TASKS:
        if not isinstance(task, dict):
            continue
        exposing = {k: v for k, v in task.items() if k not in ("when", "name", "tags")}
        body = str(exposing)
        if _SLM_OWN in body or _NODE_FILE in body or "_agent_internal_api_key" in body:
            assert task.get("no_log") is True, f"task {task.get('name')!r} passes the key to a module without no_log"


def test_the_empty_key_warning_survives():
    """The counterpart: that warning must stay visible.

    It is the node-side signal for the case where every source came back empty,
    and #14350 is about a key problem being invisible until someone reads a
    journal. Pinned so a future tightening of the rule above cannot silence it.
    """
    warning = next(
        (
            t
            for t in _TASKS
            if isinstance(t, dict) and "no internal API key could be resolved" in str(t.get("name", ""))
        ),
        None,
    )

    assert warning is not None, "the empty-key warning is gone"
    assert (
        warning.get("no_log") is not True
    ), "the empty-key warning is silenced — it reports an absent value, not a secret"


def test_the_agent_still_names_its_remedy():
    """The 401 hint is the only signal a stale key produces.

    If the message is ever removed, the failure this issue is about becomes
    undiagnosable from the node side — worth failing loudly rather than
    discovering it during the next incident.
    """
    agent = _ROLE.parent.parent / "files" / "slm" / "agent" / "agent.py"
    text = agent.read_text(encoding="utf-8")

    assert re.search(r"401", text), "the agent no longer reports a 401 on rejected heartbeats"
    assert "deploy-slm-agent" in text, "the agent no longer names the playbook that repairs it"
