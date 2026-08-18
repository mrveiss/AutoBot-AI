# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Observation must not promote a node into slm_server (#14513).

Live failure: a node whose declared roles were ``[vnc, slm-agent]`` was targeted
by ``update-all-nodes.yml``'s "Play 1 - Update SLM Server First". Play 1 deployed
the manager's backend, frontend and shared tree onto it and then died on::

    git -C /opt/autobot/code_source rev-parse HEAD   ->  rc 128
    fatal: cannot change to '/opt/autobot/code_source': No such file or directory

The node reached ``slm_server`` through ``detected_roles``, which recorded every
role the agent PROBED rather than the ones it found. Two nodes running entirely
different things reported byte-identical 20-entry lists.

Two independent defences are asserted here, because either alone is
insufficient:

1. the report filter, so the false data stops being recorded; and
2. the inventory guard, because a node this bug already contaminated will
   legitimately detect ``slm-backend`` afterwards -- the filter cannot help it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

_SLM_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, relative: str):
    """Load a module from disk, past the package conftest's `services.*` stubs.

    No `sys.path` mutation: `inventory_builder` imports nothing from `services.*`
    or `api.*`, only `autobot_shared`, which pytest.ini already puts on the path.
    pytest.ini keeps `autobot-backend/` and `autobot-slm-backend/` in separate
    invocations precisely because they define identically-named top-level
    packages, and a stray path insert is how that separation gets undone.

    The module is registered under a private name and removed again, mirroring
    `inventory_builder_agent_group_test.py`.
    """
    spec = importlib.util.spec_from_file_location(name, _SLM_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


inventory_builder = _load("inventory_builder_under_test", "services/inventory_builder.py")


def _node(declared, detected):
    return SimpleNamespace(roles=list(declared), detected_roles=list(detected))


def _groups(node):
    """Groups this node ends up in, guard applied — what the inventory writes."""
    return inventory_builder._strip_undeclared_privileged_groups(
        node, inventory_builder.groups_for_role_tokens(inventory_builder._union_roles(node))
    )


# The full catalogue every agent probes, as observed live on both nodes.
_PROBED = [
    "ai-stack",
    "autobot-llm-cpu",
    "autobot-llm-gpu",
    "autobot_shared",
    "backend",
    "browser-service",
    "celery",
    "chromadb",
    "frontend",
    "npu-worker",
    "postgres",
    "redis",
    "scheduler",
    "slm-agent",
    "slm-backend",
    "slm-database",
    "slm-frontend",
    "slm-monitoring",
    "tts-worker",
    "vnc",
]


def test_the_module_really_loaded():
    """A stubbed module would satisfy every attribute lookup below."""
    assert callable(inventory_builder.groups_for_role_tokens)
    assert callable(inventory_builder._strip_undeclared_privileged_groups)
    assert "slm_server" in inventory_builder._DECLARED_ONLY_GROUPS


def test_detection_still_adds_ordinary_groups():
    """Deliberately NOT narrowed to declared roles only.

    My first attempt at this fix made `_union_roles` return declared roles
    alone. CI caught it: `test_detected_roles_merged_with_roles` pins a real
    contract -- a node running redis that nobody declared still needs the redis
    plays to reach it. Detection adding ordinary groups is a feature.

    The defect is narrower than "detection is used at all", so the fix is too.
    """
    node = _node(["backend"], ["redis"])
    groups = _groups(node)

    assert (
        "backend" in groups and "redis" in groups
    ), "detection no longer contributes ordinary groups — this fix was over-broad"


def test_a_node_that_declares_nothing_still_gets_groups_from_detection():
    node = _node([], ["backend", "redis"])

    assert "backend" in _groups(node)


def test_a_vnc_node_does_not_join_slm_server():
    """The exact live failure.

    `slm_server` is what "Play 1 - Update SLM Server First" targets.
    """
    node = _node(["vnc", "slm-agent"], _PROBED)
    groups = _groups(node)

    assert "slm_server" not in groups, (
        "a vnc/slm-agent node is still in slm_server — Play 1 will deploy the manager tree "
        "onto it and fail on the missing code_source checkout (#14513)"
    )


def test_an_already_contaminated_node_still_does_not_join_slm_server():
    """The case the report filter cannot fix.

    This bug unpacked the SLM tree onto fleet nodes, so their agents will now
    report slm-backend as genuinely installed — a true detection of a state the
    bug itself created. Declared roles are what must decide.
    """
    node = _node(["vnc", "slm-agent"], ["slm-backend", "slm-frontend", "vnc", "slm-agent"])
    groups = _groups(node)

    assert (
        "slm_server" not in groups
    ), "a contaminated node re-qualifies for slm_server, so the failure repeats every update"


def test_the_real_manager_keeps_slm_server():
    """The guard must not lock the actual manager out of its own play."""
    node = _node(["slm-backend", "slm-frontend", "slm-database", "slm-monitoring"], _PROBED)
    groups = _groups(node)

    assert "slm_server" in groups, "the SLM manager lost slm_server — Play 1 would never run"


def test_non_privileged_groups_are_left_alone():
    """Only manager-only groups are declaration-gated.

    Narrowing everything would be a different, larger behaviour change; this
    fix is scoped to the group whose play is destructive on the wrong host.
    """
    node = _node([], ["backend"])
    groups = _groups(node)

    assert "backend" in groups, "a detection-only node lost its ordinary groups"


def test_a_contaminated_node_is_also_kept_out_of_the_backend_group():
    """Review of #14513: `slm_server` alone was under-inclusive.

    Play 2 unarchives autobot-backend onto any host with `'backend' in
    group_names` and runs the alembic upgrade sequence there. It also sets
    `any_errors_fatal: true` with `serial: 3`, so a single wrongly-included node
    aborts the whole batch of legitimate hosts -- a wider blast radius than the
    Play 1 failure that surfaced this bug.

    The same contamination that put the SLM tree on a VNC node would have put
    the backend tree there too, and detection would then keep re-granting it.
    """
    node = _node(["vnc", "slm-agent"], ["slm-backend", "backend", "vnc", "slm-agent"])
    groups = _groups(node)

    assert "backend" not in groups, "a node that never declared backend is still a backend deploy target"
    assert "main" not in groups, "`main` is granted alongside `backend` and must be gated with it"


def test_a_declared_backend_node_keeps_its_groups():
    """The gate must not lock a real backend node out of its own deploy."""
    groups = _groups(_node(["backend"], ["backend"]))

    assert "backend" in groups and "main" in groups


def test_ordinary_groups_are_still_granted_by_detection():
    """The line is drawn at deploy targets, not at "detection is untrusted".

    A node genuinely running redis should keep receiving redis updates, which
    `test_detected_roles_merged_with_roles` pins independently.
    """
    groups = _groups(_node(["vnc"], ["redis"]))

    assert "redis" in groups and "database" in groups
