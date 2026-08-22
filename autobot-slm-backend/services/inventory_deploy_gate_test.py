# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Detection must not make a node any deploy target (#14567).

#14513 stopped detection granting `slm_server`; #14552 added the rest of the
groups `update-all-nodes.yml` gates on. Both enumerated names, and both were
too short — other playbooks target the SIBLING names the same role grants:

    setup-ai-stack.yml    -> hosts: ai_stack     (the gate held only `aiml`)
    setup-npu-worker.yml  -> hosts: npu_worker   (the gate held only `npu`)

both reachable from `/infrastructure/execute`, where `limit_hosts` is optional.

So the set is now derived by closing over `_ROLE_TO_GROUPS` rather than listed.
Two properties of that closure are load-bearing and pinned below.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

_SLM_ROOT = Path(__file__).resolve().parent.parent


def _load():
    name = "_inventory_builder_deploy_gate"
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


def test_the_closure_widened_the_seed():
    """A closure that added nothing would leave every rule here vacuous."""
    seed = set(inventory_builder._DEPLOY_GATED_SEED)
    gated = set(inventory_builder._DECLARED_ONLY_GROUPS)

    assert seed <= gated, "the seed must survive — those names came from deploy gates directly"
    assert gated - seed, "the closure added nothing; _ROLE_TO_GROUPS or the seed changed shape"


def test_sibling_deploy_groups_are_gated():
    """The #14567 gap: the names other playbooks target by `hosts:`."""
    gated = set(inventory_builder._DECLARED_ONLY_GROUPS)

    for sibling in ("ai_stack", "npu_worker", "npu_workers", "browser_worker"):
        assert sibling in gated, f"{sibling} is a `hosts:` target but detection can still grant it"


def test_agent_membership_stays_ungated():
    """The refinement without which this change would be worse than the bug.

    The `slm-` prefix role grants `slm`/`slm_nodes` alongside `slm_server`, so a
    naive closure gates them — and `deploy-slm-agent.yml` targets `slm_nodes`.
    That would withhold the agent-repair playbook from agent nodes: the remedy
    the agent's own 401 message names (#14350 / #14351) becomes unreachable for
    exactly the nodes needing it.

    `slm-agent` is not a deploy target, so the groups it shares stay broad.
    """
    gated = set(inventory_builder._DECLARED_ONLY_GROUPS)

    assert "slm_nodes" not in gated, "deploy-slm-agent.yml could no longer reach an agent node"
    assert "slm" not in gated
    assert "slm_nodes" in _groups(_node([], ["slm-agent"]))


def test_a_detection_only_node_is_no_deploy_target():
    """The live shape: a node whose detection reported the whole catalogue."""
    node = _node(
        ["vnc", "slm-agent"],
        ["ai-stack", "npu-worker", "browser-service", "frontend", "backend", "slm-backend", "redis", "vnc"],
    )
    groups = _groups(node)

    for leaked in (
        "ai_stack",
        "npu_worker",
        "npu_workers",
        "browser_worker",
        "aiml",
        "npu",
        "browser",
        "frontend",
        "backend",
        "slm_server",
    ):
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
        ("tts-worker", "ai_stack"),
    ):
        assert expected in _groups(_node([role], [role])), f"declared {role} lost {expected}"
