# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Gating the group a play NAMES leaves the siblings it does not (#14567).

#14552 gated the group names `update-all-nodes.yml` tests in its
`when: "'x' in group_names"` gates. But `_ROLE_TO_GROUPS` grants siblings
alongside each of those, and other playbooks target the siblings directly:

* `setup-ai-stack.yml`    -> `hosts: ai_stack`   (gate covered only `aiml`)
* `setup-npu-worker.yml`  -> `hosts: npu_worker` (gate covered only `npu`)

Both reachable from the same `/infrastructure/execute` surface, where
`limit_hosts` is optional. A node that never declared ai-stack kept `ai_stack`
and would have received the full provisioning playbook.

So the gate is now DERIVED by closing over the role map rather than listing
names — the third time in this area that an enumerated list proved too short.

The closure needed one refinement, pinned below, because the naive form
introduced a worse bug than it fixed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

_SLM_ROOT = Path(__file__).resolve().parent.parent


def _load():
    name = "_inventory_builder_siblings"
    spec = importlib.util.spec_from_file_location(name, _SLM_ROOT / "services" / "inventory_builder.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


inventory_builder = _load()


def _node(declared, detected):
    return SimpleNamespace(roles=list(declared), detected_roles=list(detected))


def _groups(node):
    return inventory_builder._strip_undeclared_privileged_groups(
        node, inventory_builder.groups_for_role_tokens(inventory_builder._union_roles(node))
    )


def test_the_closure_actually_widened_the_seed():
    """A closure that added nothing would leave this rule vacuous."""
    seed = set(inventory_builder._DEPLOY_GATED_SEED)
    gated = set(inventory_builder._DECLARED_ONLY_GROUPS)

    assert seed <= gated, "the seed must always survive — those names came from deploy gates directly"
    assert gated - seed, "the closure added nothing; _ROLE_TO_GROUPS or the seed changed shape"


def test_sibling_deploy_groups_are_gated_too(
):
    """The #14567 gap: the names other playbooks target by `hosts:`."""
    gated = set(inventory_builder._DECLARED_ONLY_GROUPS)

    for sibling in ("ai_stack", "npu_worker", "npu_workers", "browser_worker"):
        assert sibling in gated, (
            f"{sibling} is targeted by a setup playbook via `hosts:` but detection can still grant it"
        )


def test_agent_membership_groups_are_NOT_gated():
    """The regression the naive closure introduced, pinned so it cannot return.

    The `slm-` prefix role grants `slm`/`slm_nodes` alongside `slm_server`, so
    closing over the role map gates them too. But `slm-agent` grants them as
    well and is not a deploy target — and `deploy-slm-agent.yml` targets
    `slm_nodes`.

    Gating them would have withheld the agent-repair playbook from agent nodes:
    the remedy the agent's own 401 message names (#14350 / #14351) would have
    been unreachable for exactly the nodes needing it.
    """
    gated = set(inventory_builder._DECLARED_ONLY_GROUPS)

    assert "slm_nodes" not in gated, "deploy-slm-agent.yml could no longer reach an agent node"
    assert "slm" not in gated


def test_a_detection_only_agent_node_keeps_its_agent_groups():
    """Behavioural counterpart to the rule above."""
    groups = _groups(_node([], ["slm-agent"]))

    assert "slm_nodes" in groups and "slm" in groups


def test_a_contaminated_node_leaks_no_deploy_group():
    """The live shape: a vnc node whose detection reports the whole catalogue."""
    node = _node(
        ["vnc", "slm-agent"],
        ["ai-stack", "npu-worker", "browser-service", "frontend", "backend", "slm-backend", "redis", "vnc", "slm-agent"],
    )
    groups = _groups(node)

    for leaked in ("ai_stack", "npu_worker", "npu_workers", "browser_worker", "aiml", "npu", "browser", "frontend", "backend", "slm_server"):
        assert leaked not in groups, f"{leaked} still granted by detection alone"

    assert "redis" in groups, "ordinary groups must still come from detection"
    assert "slm_nodes" in groups, "the node declares slm-agent, so it keeps its agent groups"


def test_declared_roles_keep_every_group_they_grant():
    """The gate must never lock a role out of its own deploy."""
    for role, expected in (
        ("ai-stack", "ai_stack"),
        ("npu-worker", "npu_workers"),
        ("browser-service", "browser_worker"),
        ("slm-backend", "slm_server"),
        ("frontend", "frontend"),
    ):
        assert expected in _groups(_node([role], [role])), f"declared {role} lost {expected}"
