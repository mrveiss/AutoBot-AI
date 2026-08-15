# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A node too stale to heartbeat must still be updatable (#14297).

#11511 skipped non-operational nodes outright, reasoning that a deploy against
them "will always fail". That is true of a node that is down. It is not true of
a node that is merely unhealthy — and the case where the two diverge is a
deadlock:

    the agent is too old to heartbeat
      -> the node is marked degraded
        -> update-all skips degraded nodes
          -> the node never receives the update that would replace the agent

Observed live: a fleet node 1140 commits behind, SSH-reachable, remediation
looping three attempts at a time for hours and never succeeding, skipped on
every update-all.

The fix does not add a reachability probe. Ansible already reports UNREACHABLE
distinctly from a failure, so the attempt goes ahead and that verdict decides.
The tests below are about the two ways this could go wrong: a genuinely down
node must still not fail the job, and a broken deploy must NOT be able to
report itself as "node was down".
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_ansible_utils():
    """The shared parser, loaded standalone — it imports only stdlib + env_utils."""
    spec = importlib.util.spec_from_file_location("_au_14297", _BACKEND_ROOT / "services" / "ansible_utils.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_au_14297"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_au_14297", None)
    return module


_au = _load_ansible_utils()

_UNREACHABLE_OUTPUT = """
PLAY [Update fleet node] *******************************************************

TASK [Gathering Facts] *********************************************************
fatal: [vnc-node]: UNREACHABLE! => {"changed": false, "msg": "Failed to connect to the host via ssh", "unreachable": true}

PLAY RECAP *********************************************************************
vnc-node                   : ok=0    changed=0    unreachable=1    failed=0
"""

_FAILED_OUTPUT = """
PLAY [Update fleet node] *******************************************************

TASK [Install packages] ********************************************************
fatal: [vnc-node]: FAILED! => {"changed": true, "msg": "ERROR: Cannot install tokenizers"}

PLAY RECAP *********************************************************************
vnc-node                   : ok=3    changed=1    unreachable=0    failed=1
"""


def _node(node_id="b9a29e04", hostname="vnc-node", ip="10.0.0.9"):
    return SimpleNamespace(node_id=node_id, hostname=hostname, ip_address=ip)


# --------------------------------------------------------------------------
# The parser the decision rests on
# --------------------------------------------------------------------------


def test_an_unreachable_host_is_extracted():
    assert _au.parse_unreachable_hosts(_UNREACHABLE_OUTPUT) == ["vnc-node"]


def test_a_failed_host_is_not_reported_as_unreachable():
    """The distinction the whole fix rests on.

    If a plain failure parsed as unreachable, every broken deploy against a
    degraded node would be recorded as a skip — the job would go green and the
    node would stay stale, which is the bug this is meant to end.
    """
    assert _au.parse_unreachable_hosts(_FAILED_OUTPUT) == []


def test_empty_and_missing_output_are_handled():
    assert _au.parse_unreachable_hosts("") == []
    assert _au.parse_unreachable_hosts(None) == []


def test_each_host_is_reported_once_in_order():
    doubled = _UNREACHABLE_OUTPUT + _UNREACHABLE_OUTPUT.replace("vnc-node", "other-node") + _UNREACHABLE_OUTPUT
    assert _au.parse_unreachable_hosts(doubled) == ["vnc-node", "other-node"]


# --------------------------------------------------------------------------
# Matching the verdict back to the node
# --------------------------------------------------------------------------


def _was_unreachable(node, output: str) -> bool:
    """Mirror of ``code_sync._node_was_unreachable`` over the shared parser.

    Reimplemented rather than imported because ``api/code_sync.py`` pulls in
    the whole backend; the identity-matching rule is what is under test and it
    is three lines. ``test_the_production_helper_matches_this_rule`` below pins
    the two together so this cannot drift into testing itself.
    """
    unreachable = _au.parse_unreachable_hosts(output or "")
    if not unreachable:
        return False
    identities = {node.node_id, node.hostname, node.ip_address} - {None, ""}
    return bool(identities & set(unreachable))


@pytest.mark.parametrize("attr", ["node_id", "hostname", "ip_address"])
def test_the_node_is_matched_on_any_of_its_identities(attr):
    """Ansible's inventory name is not reliably the DB's hostname.

    ``ansible_hostname`` is the OS hostname while ``nodes.hostname`` is a
    display name — #1789 hit exactly this and fell back to IP.
    """
    node = _node()
    output = _UNREACHABLE_OUTPUT.replace("vnc-node", getattr(node, attr))

    assert _was_unreachable(node, output)


def test_another_nodes_unreachability_is_not_this_nodes():
    """A multi-host run must not let one down host excuse a different one."""
    node = _node()
    output = _UNREACHABLE_OUTPUT.replace("vnc-node", "some-other-node")

    assert not _was_unreachable(node, output)


def test_a_failure_is_not_treated_as_unreachable():
    assert not _was_unreachable(_node(), _FAILED_OUTPUT)


def test_the_production_helper_matches_this_rule():
    """Pin the mirror above to the real implementation.

    Read as source because importing ``api/code_sync.py`` pulls in the backend;
    the check is that the real helper consults the shared parser and matches on
    all three identities, which is what the mirror encodes.
    """
    source = (_BACKEND_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
    start = source.index("def _node_was_unreachable(")
    body = source[start : source.index("\ndef ", start + 1)]

    assert "parse_unreachable_hosts(" in body
    for identity in ("node.node_id", "node.hostname", "node.ip_address"):
        assert identity in body, f"{identity} is not consulted — an inventory name mismatch would misreport"


# --------------------------------------------------------------------------
# The skip must be gone from the health check itself
# --------------------------------------------------------------------------


def test_a_non_operational_node_is_no_longer_skipped_before_the_attempt():
    """The deadlock-breaker, asserted on control flow rather than on a log line.

    ``_sync_fleet_node`` must not return early on ``_is_node_operational``.
    Checked structurally: within the function, no ``return`` may appear inside
    a branch guarded by that predicate before the playbook is executed.
    """
    import ast

    source = (_BACKEND_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_sync_fleet_node"
    )

    guards = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.If)
        and any(
            isinstance(call, ast.Call) and getattr(call.func, "id", None) == "_is_node_operational"
            for call in ast.walk(node.test)
        )
    ]
    for guard in guards:
        returns = [n for n in ast.walk(guard) if isinstance(n, ast.Return)]
        assert not returns, "a non-operational node still returns before the update is attempted (#14297)"


def test_the_operational_predicate_is_still_consulted():
    """It must still be *used* — the fix reclassifies the node, it does not stop looking.

    Deleting the check entirely would also pass the rule above while losing the
    "attempting anyway" signal and the unreachable-is-a-skip handling, which
    both depend on knowing the node was unhealthy.
    """
    source = (_BACKEND_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
    start = source.index("async def _sync_fleet_node(")
    body = source[start : source.index("\nasync def ", start + 1)]

    assert "_is_node_operational(node)" in body
