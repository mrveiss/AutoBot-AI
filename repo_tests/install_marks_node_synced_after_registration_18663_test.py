# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""install.sh marks the local node synced AFTER it registers it (#18663).

The mark-synced endpoint 404s on a node with no row, and the playbook tolerates that 404 for the
fleet-wide run. During ``ansible_deployment`` the local node is not registered yet, so a
mark-synced step placed there passes silently and stamps nothing. The step belongs after
``register_local_node``, and must reuse the playbook's tagged tasks.
"""

from __future__ import annotations

from repo_tests._paths import repo_root

_SCRIPT = "scripts/deployment/mark_local_node_synced.sh"
_REGISTER = "register_local_node() {"


def _register_body(source: str) -> str:
    """install.sh's register_local_node function body."""
    return source[source.index(_REGISTER) :].split("\n}\n", 1)[0]


def _marks_after_registration(source: str) -> bool:
    """The mark-synced call sits inside register_local_node, after the node POST."""
    body = _register_body(source)
    return _SCRIPT in body and body.index(_SCRIPT) > body.index('"${api_url}/api/nodes"')


def _install() -> str:
    return (repo_root() / "install.sh").read_text(encoding="utf-8")


def test_mark_synced_runs_after_registration() -> None:
    assert _marks_after_registration(_install())


def test_control_call_before_registration_fails() -> None:
    source = _install()
    line = next(ln for ln in source.splitlines() if _SCRIPT in ln)
    moved = source.replace(line + "\n", "").replace(_REGISTER + "\n", _REGISTER + "\n" + line + "\n", 1)
    assert moved != source, "control did not change install.sh"
    assert not _marks_after_registration(moved)


def test_mark_synced_reuses_the_playbook_tasks() -> None:
    script = (repo_root() / _SCRIPT).read_text(encoding="utf-8")
    assert "playbooks/provision-fleet-roles.yml" in script and "--tags mark-synced" in script
    assert "/api/code-sync/" not in script, "a second hand-written call to the endpoint"
