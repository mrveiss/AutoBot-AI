# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The slm-agent must not put a fleet node in slm_server (#14328).

`_ROLE_TO_GROUPS` had one `"slm-"` prefix key covering the manager's own
components — `slm-backend`, `slm-frontend`, `slm-database`, `slm-monitoring` —
and it also caught `slm-agent`, which runs on **every** fleet node.

So every agent-carrying node joined `slm_server`, and
`update-all-nodes.yml`'s "Play 1 - Update SLM Server First" ran against it:

    git -c safe.directory=/opt/autobot/code_source \\
        -C /opt/autobot/code_source rev-parse HEAD \\
        > /opt/autobot/autobot-slm-backend/.deployed_commit

Neither path exists on a node that is not the manager, so the task failed with
a non-zero rc and halted the entire fleet stage.

Observed live on a VNC node. It was invisible until #14297 stopped skipping
degraded nodes — #11511's skip had been hiding it, so the play never ran
against a fleet node to fail on.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("_ib_14328", _BACKEND_ROOT / "services" / "inventory_builder.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ib_14328"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_ib_14328", None)
    return module


_ib = _load()

# Plays in update-all-nodes.yml that assume the manager's own filesystem —
# /opt/autobot/code_source and /opt/autobot/autobot-slm-backend.
_MANAGER_ONLY_GROUP = "slm_server"


@pytest.mark.parametrize(
    "roles",
    [
        ["slm-agent"],
        ["slm_agent"],
        ["vnc", "slm-agent"],
        ["npu-worker", "slm-agent"],
        ["browser-service", "slm-agent"],
    ],
)
def test_a_node_carrying_only_the_agent_is_not_an_slm_server(roles):
    """The agent alone must never imply the manager.

    Parametrised over the role combinations a real fleet node carries, because
    the defect was in a *prefix* match — it fires for any token starting with
    `slm-`, so the guard has to cover the shapes that actually occur rather
    than the one that was reported.
    """
    groups = _ib.groups_for_role_tokens(roles)

    assert _MANAGER_ONLY_GROUP not in groups, (
        f"roles {roles} put the node in {_MANAGER_ONLY_GROUP}, so Play 1 of "
        "update-all-nodes.yml would run the manager's update against it (#14328)"
    )


@pytest.mark.parametrize(
    "role",
    ["slm-backend", "slm-frontend", "slm-database", "slm-monitoring"],
)
def test_the_managers_own_components_still_are(role):
    """The other half, which the fix must not break.

    Removing `slm_server` from the agent is only correct while the manager
    still reaches it by its own roles. A fix that dropped everyone from
    `slm_server` would satisfy the rule above and silently stop updating the
    manager.
    """
    assert _MANAGER_ONLY_GROUP in _ib.groups_for_role_tokens([role])


def test_the_real_manager_role_set_is_still_an_slm_server():
    """The live manager carries all four plus the agent."""
    manager = ["slm-backend", "slm-frontend", "slm-database", "slm-monitoring", "slm-agent"]

    assert _MANAGER_ONLY_GROUP in _ib.groups_for_role_tokens(manager)


def test_the_agent_still_joins_the_fleet_groups():
    """It must lose `slm_server` without losing everything.

    `slm_nodes` is what the agent-management plays target; dropping it would
    trade a wrong-play bug for a never-managed one.
    """
    groups = _ib.groups_for_role_tokens(["vnc", "slm-agent"])

    assert "slm_nodes" in groups
    assert "slm" in groups


def test_the_exact_key_beats_the_prefix():
    """Why the fix works at all, pinned so a reorder cannot silently undo it.

    `_role_tokens_to_groups` checks exact keys first and `continue`s, so the
    explicit `slm-agent` entry wins over the `slm-` prefix. If that ordering
    were ever inverted, the agent would inherit `slm_server` again and every
    test above would fail — this one names the mechanism so the failure is
    diagnosable rather than mysterious.
    """
    assert "slm-agent" in _ib._ROLE_TO_GROUPS, "the exact key is gone; the prefix would take over"
    assert _MANAGER_ONLY_GROUP not in _ib._ROLE_TO_GROUPS["slm-agent"]
    assert _MANAGER_ONLY_GROUP in _ib._ROLE_TO_GROUPS["slm-"]
