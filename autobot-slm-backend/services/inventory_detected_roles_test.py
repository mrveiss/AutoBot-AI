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
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load(name: str, relative: str):
    """Load a module from disk, past the package conftest's `services.*` stubs."""
    spec = importlib.util.spec_from_file_location(name, _SLM_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


inventory_builder = _load("inventory_builder_under_test", "services/inventory_builder.py")


def _node(declared, detected):
    return SimpleNamespace(roles=list(declared), detected_roles=list(detected))


# The full catalogue every agent probes, as observed live on both nodes.
_PROBED = [
    "ai-stack", "autobot-llm-cpu", "autobot-llm-gpu", "autobot_shared", "backend",
    "browser-service", "celery", "chromadb", "frontend", "npu-worker", "postgres",
    "redis", "scheduler", "slm-agent", "slm-backend", "slm-database", "slm-frontend",
    "slm-monitoring", "tts-worker", "vnc",
]


def test_the_module_really_loaded():
    """A stubbed module would satisfy every attribute lookup below."""
    assert callable(inventory_builder.groups_for_role_tokens)
    assert callable(inventory_builder._strip_undeclared_privileged_groups)
    assert "slm_server" in inventory_builder._DECLARED_ONLY_GROUPS


def test_declared_roles_decide_what_a_node_runs():
    """Detection is an observation, not an instruction."""
    node = _node(["vnc", "slm-agent"], _PROBED)

    assert inventory_builder._union_roles(node) == ["vnc", "slm-agent"], (
        "detected roles are still deciding what the node runs (#14513)"
    )


def test_a_node_that_declares_nothing_still_falls_back_to_detection():
    """Dropping the fallback would stop plays reaching such a node entirely."""
    node = _node([], ["backend", "redis"])

    assert inventory_builder._union_roles(node) == ["backend", "redis"]


def test_a_vnc_node_does_not_join_slm_server():
    """The exact live failure.

    `slm_server` is what "Play 1 - Update SLM Server First" targets.
    """
    node = _node(["vnc", "slm-agent"], _PROBED)
    groups = inventory_builder._strip_undeclared_privileged_groups(
        node, inventory_builder.groups_for_role_tokens(inventory_builder._union_roles(node))
    )

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
    groups = inventory_builder._strip_undeclared_privileged_groups(
        node, inventory_builder.groups_for_role_tokens(inventory_builder._union_roles(node))
    )

    assert "slm_server" not in groups, (
        "a contaminated node re-qualifies for slm_server, so the failure repeats every update"
    )


def test_the_real_manager_keeps_slm_server():
    """The guard must not lock the actual manager out of its own play."""
    node = _node(["slm-backend", "slm-frontend", "slm-database", "slm-monitoring"], _PROBED)
    groups = inventory_builder._strip_undeclared_privileged_groups(
        node, inventory_builder.groups_for_role_tokens(inventory_builder._union_roles(node))
    )

    assert "slm_server" in groups, "the SLM manager lost slm_server — Play 1 would never run"


def test_non_privileged_groups_are_left_alone():
    """Only manager-only groups are declaration-gated.

    Narrowing everything would be a different, larger behaviour change; this
    fix is scoped to the group whose play is destructive on the wrong host.
    """
    node = _node([], ["backend"])
    groups = inventory_builder._strip_undeclared_privileged_groups(
        node, inventory_builder.groups_for_role_tokens(inventory_builder._union_roles(node))
    )

    assert "backend" in groups, "a detection-only node lost its ordinary groups"
