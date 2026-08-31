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

import ast
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

    # #14681: this was a hand-written list of ten names and had drifted — it
    # omitted `llm_nodes`, `ai` and `main`, so three gated groups had no
    # detection-leak assertion at all. Derived from the gate itself now, which
    # is the only version that cannot fall behind it.
    gated = set(inventory_builder._DECLARED_ONLY_GROUPS)
    assert {"llm_nodes", "ai", "main"} <= gated, "the gate no longer covers the groups this test was missing"
    for leaked in sorted(gated):
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


# ---------------------------------------------------------------------------
# #14681 — the derived gate must not be able to shrink unnoticed
# ---------------------------------------------------------------------------


def test_every_gated_group_is_pinned_by_name() -> None:
    """The gate is derived, so a change to the role map can silently shrink it.

    Four of the six derived names were pinned; `llm_nodes` and `ai` appeared
    nowhere in this file, and neither did the seed name `main`. A group that
    drops out of the gate stops being stripped from an undeclared node, which
    reopens the privileged path the gate exists to close — silently, because
    nothing asserted it was ever in there.

    Pinned as a whole set rather than by adding two more names: the next group
    to appear would otherwise be unpinned in exactly the same way.
    """
    from services.inventory_builder import _DECLARED_ONLY_GROUPS

    expected = {
        # seed (#14552)
        "slm_server",
        "backend",
        "main",
        "frontend",
        "aiml",
        "npu",
        "browser",
        # derived by _close_over_role_groups (#14567)
        "ai",
        "ai_stack",
        "browser_worker",
        "llm_nodes",
        "npu_worker",
        "npu_workers",
    }
    assert set(_DECLARED_ONLY_GROUPS) == expected, (
        "the deploy gate changed. If a group was added, add it above. If one was REMOVED, "
        "check that an undeclared node can no longer reach whatever that group provisions "
        f"before updating this test.\n  missing: {sorted(expected - set(_DECLARED_ONLY_GROUPS))}"
        f"\n  unexpected: {sorted(set(_DECLARED_ONLY_GROUPS) - expected)}"
    )


def test_declaring_a_vector_database_does_not_activate_the_llm_runtime() -> None:
    """#14682: chromadb and tts-worker grant ai_stack but do not run an LLM.

    Asserted on the role map rather than on the jinja: `llm_nodes` is the signal
    `role_llm_active` now uses, so what matters is which tokens reach it.
    """
    from services.inventory_builder import _ROLE_TO_GROUPS

    llm_tokens = {token for token, groups in _ROLE_TO_GROUPS.items() if "llm_nodes" in groups}
    assert "chromadb" not in llm_tokens, "declaring chromadb would run the ollama installer"
    assert "tts-worker" not in llm_tokens, "declaring tts-worker would run the ollama installer"
    assert llm_tokens, "no token grants llm_nodes — role_llm_active could never fire"


def _legacy_role_groups() -> dict:
    """`ROLE_ANSIBLE_GROUPS` read from source, without importing role_registry.

    #14307's guard is right to object to importing it here: conftest does not
    real-load `role_registry` (it pulls SQLAlchemy, above the dependency-light
    bar that list holds to), so an import resolves to a MagicMock or not
    depending on shard order — and a MagicMock iterates as empty, which would
    make this test pass by examining nothing.

    Parsing the literal is deterministic and needs no import at all.
    """
    src = (_SLM_ROOT / "services" / "role_registry.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        target = None
        if isinstance(node, ast.AnnAssign):
            target = getattr(node.target, "id", None)
        elif isinstance(node, ast.Assign) and node.targets:
            target = getattr(node.targets[0], "id", None)
        if target == "ROLE_ANSIBLE_GROUPS":
            return ast.literal_eval(node.value)
    raise AssertionError("ROLE_ANSIBLE_GROUPS not found — this guard would pass vacuously")


def test_the_legacy_vocabulary_cannot_grant_a_gated_group_by_detection() -> None:
    """#14681: the legacy `ROLE_ANSIBLE_GROUPS` is a second way to reach a group.

    `_close_over_role_groups` closes over `_ROLE_TO_GROUPS` only. If the legacy
    map grants a gated group for a token the primary map does not, detection
    through that route would bypass the closure's reasoning entirely. `vnc`
    reaches its group solely through that map (#14638), so it is a live path,
    not a theoretical one.
    """
    legacy = _legacy_role_groups()
    assert legacy, "the legacy map is empty — nothing would be checked"

    gated = set(inventory_builder._DECLARED_ONLY_GROUPS)
    for token, granted in legacy.items():
        names = {granted} if isinstance(granted, str) else set(granted or ())
        privileged = names & gated
        if not privileged:
            continue
        leaked = _groups(_node(declared=[], detected=[token])) & privileged
        assert not leaked, (
            f"the legacy vocabulary lets detected token {token!r} grant gated group(s) {sorted(leaked)} "
            "— the closure only reasons about _ROLE_TO_GROUPS"
        )


def test_a_new_non_deploy_role_shrinks_the_gate_and_the_pin_catches_it() -> None:
    """#14681: the failure mode is a role added later, not a group edited today.

    `_close_over_role_groups` excuses any group also granted by a role that
    intersects no seed name (`shared_with_non_deploy`). So adding a token that
    grants `llm_nodes` and nothing seed-adjacent does not widen the gate — it
    REMOVES `llm_nodes` from it, because the group now looks shared with a
    non-deploy role. Detection would then hand out `llm_nodes`, which is the
    root-level ollama install path (#14682).

    Nothing about that edit looks dangerous in review: a role is added to a map
    and a group silently loses its gating. The set-equality pin above is what
    turns it into a failing test, so this asserts the mechanism directly rather
    than trusting that it will be noticed.
    """
    original = dict(inventory_builder._ROLE_TO_GROUPS)
    try:
        before = set(inventory_builder._close_over_role_groups(inventory_builder._DEPLOY_GATED_SEED))
        assert "llm_nodes" in before, "llm_nodes is not gated to begin with — this test proves nothing"

        inventory_builder._ROLE_TO_GROUPS["some-future-llm-role"] = frozenset({"llm_nodes"})
        after = set(inventory_builder._close_over_role_groups(inventory_builder._DEPLOY_GATED_SEED))

        assert "llm_nodes" not in after, (
            "the closure no longer drops a group shared with a non-deploy role. If that was fixed "
            "deliberately, this test should be replaced by one asserting the group STAYS gated."
        )
        assert before != after, "the gate did not change, so the pinned-set assertion would not catch this"
    finally:
        inventory_builder._ROLE_TO_GROUPS.clear()
        inventory_builder._ROLE_TO_GROUPS.update(original)
