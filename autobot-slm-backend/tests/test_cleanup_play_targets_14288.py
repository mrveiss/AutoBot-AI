# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every cleanup play must target something an inventory actually contains (#14288).

``cleanup-nodes.yml`` gated two plays on ``npu-worker`` and ``browser-automation``
— hyphenated spellings that **no** inventory source emits. Ansible does not
treat ``-`` and ``_`` as equivalent in group names, so both plays matched zero
hosts and skipped, on every run, through both execution stacks.

Cleanup is the operation whose whole point is that something is gone afterwards.
A no-op is indistinguishable from a successful cleanup in the run output —
``ok=0 changed=0 failed=0`` and a green result either way — while the service
this was meant to remove keeps running on the node.

Three sources can define a target, and a play needs only one of them:

* the static inventory's groups and host names
* ``services/inventory_builder.py`` — the canonical dynamic builder
* ``services/role_registry.py::ROLE_ANSIBLE_GROUPS`` — the setup-wizard map

``localhost`` is ansible's implicit host and belongs to none of them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE_DIR = _BACKEND_ROOT / "ansible"
_CLEANUP = _ANSIBLE_DIR / "playbooks" / "cleanup-nodes.yml"
_STATIC_INVENTORY = _ANSIBLE_DIR / "inventory" / "slm-nodes.yml"

# Implicit to ansible, defined by no inventory.
_IMPLICIT_HOSTS = frozenset({"localhost", "all"})


def _static_inventory_names() -> set[str]:
    """Group and host names the checked-in inventory defines.

    Parsed structurally rather than with yaml.safe_load: the file is full of
    ``{{ lookup(...) }}`` expressions, and a loader would either choke or need
    the whole templating stack to resolve them.
    """
    text = _STATIC_INVENTORY.read_text(encoding="utf-8")
    names: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"^(?P<indent>\s{4,})(?P<name>[A-Za-z0-9][\w.-]*):\s*$", line)
        if match:
            names.add(match.group("name"))
    return names


def _builder_group_names() -> set[str]:
    """Every group name either dynamic builder can emit."""
    names: set[str] = set()

    builder = (_BACKEND_ROOT / "services" / "inventory_builder.py").read_text(encoding="utf-8")
    tree = ast.parse(builder)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in {
            "_ROLE_TO_GROUPS",
            "_UNIVERSAL_NON_SLM",
            "_UNIVERSAL_ALL",
            "REQUIRED_GROUPS",
        }:
            names.update(
                child.value
                for child in ast.walk(node.value)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            )

    registry = (_BACKEND_ROOT / "services" / "role_registry.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(registry)):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "ROLE_ANSIBLE_GROUPS":
            names.update(
                child.value
                for child in ast.walk(node.value)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            )
    return names


def _cleanup_targets() -> list[tuple[int, str]]:
    """Every ``hosts:`` token in the cleanup playbook, with its line number."""
    targets: list[tuple[int, str]] = []
    for number, line in enumerate(_CLEANUP.read_text(encoding="utf-8").splitlines(), 1):
        match = re.match(r"^\s*hosts:\s*([^#]+)", line)
        if not match:
            continue
        for token in re.split(r"[,:]", match.group(1)):
            token = token.strip().strip("\"'")
            if token and not token.startswith("{{"):
                targets.append((number, token))
    return targets


def test_the_scan_finds_the_cleanup_plays():
    """An empty scan reads exactly like a clean one."""
    assert _cleanup_targets(), f"no `hosts:` found in {_CLEANUP.name} — the scan is broken, not the playbook"


def test_the_inventory_sources_are_non_empty():
    """Likewise for the other half of the comparison.

    If either parser silently returned nothing, every target below would be
    reported unresolvable — or, worse, the rule would be comparing against an
    empty set and passing for the wrong reason.
    """
    assert _static_inventory_names(), "parsed no names out of the static inventory"
    assert _builder_group_names(), "parsed no group names out of either dynamic builder"


@pytest.mark.parametrize("line,target", _cleanup_targets(), ids=lambda v: str(v))
def test_every_cleanup_target_is_defined_somewhere(line, target):
    """A hyphen-for-underscore typo makes the play skip, silently and forever.

    Written over every target rather than the two that were broken, so a third
    misspelling cannot be introduced and sit unnoticed — which is how these two
    survived: nothing failed, the plays simply never ran.
    """
    if target in _IMPLICIT_HOSTS:
        return

    known = _static_inventory_names() | _builder_group_names()
    assert target in known, (
        f"{_CLEANUP.name}:{line} targets '{target}', which no inventory source defines — "
        "the play will match zero hosts and skip while reporting success"
    )


def test_the_two_reported_spellings_are_gone():
    """Pin the specific regression, since the rule above would also pass if
    someone deleted the plays rather than fixing their targets."""
    targets = {target for _line, target in _cleanup_targets()}

    assert "npu-worker" not in targets
    assert "browser-automation" not in targets
    assert "npu_worker" in targets, "the npu-worker cleanup play is gone entirely"
    assert targets & {"browser_worker", "browser_automation"}, "the browser cleanup play is gone entirely"
