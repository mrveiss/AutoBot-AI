#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for check_canonical_role_names (#7053 / #14181).

This file did not exist until #14181 — the checker's own ALLOWLIST named it,
but nothing was there, so the rule that guards #7053's role-name migration had
no coverage of its own. Written while waking the hook, which had never run
because its exec bit was not tracked (#14181).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_canonical_role_names import ALLOWLIST, find_violations  # noqa: E402


def _write(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    return path

# --- #14181: the parenthesised spelling was invisible -------------------------


def test_a_parenthesised_node_roles_is_blocked() -> None:
    """`'X' in (node_roles | default([]))` is the same deprecated gate.

    The pattern required `node_roles` to follow `in` directly, so a gate
    written with the parenthesised default — the exact form the OR-chains in
    group_vars/all.yml use 18 times — passed the rule silently.
    """
    body = "when: \"{{ ('backend' in (node_roles | default([]))) }}\"\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "paren.yml", body)
        assert len(find_violations(f)) == 1


def test_the_unparenthesised_form_is_still_blocked() -> None:
    """Widening must not lose the shape it already caught."""
    body = "when: \"'backend' in node_roles\"\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "plain.yml", body)
        assert len(find_violations(f)) == 1


def test_the_canonical_form_still_passes() -> None:
    """A widening that flagged `autobot-X` would block the fix it recommends."""
    body = (
        "when: \"'autobot-backend' in (node_roles | default([]))\"\n"
        "when2: \"{{ role_backend_active | bool }}\"\n"
    )
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "canonical.yml", body)
        assert find_violations(f) == []


def test_the_allowlist_is_actually_enforced_not_just_declared() -> None:
    """Calls the real checker against a real allowlisted file.

    Review finding on this PR: the previous version of this test asserted only
    frozenset membership. Mutating `if rel in ALLOWLIST: return []` to
    `if False:` left all four tests passing while the checker reported 21
    violations across the three legitimately-exempt files. Membership and
    enforcement are independent, and only the second one matters.
    """
    repo = Path(__file__).resolve().parents[2]
    for name in sorted(ALLOWLIST):
        if not name.endswith((".yml", ".yaml")):
            continue  # the checker only scans YAML; its own sources are moot
        path = repo / name
        if not path.is_file():  # pragma: no cover - file moved
            continue
        assert find_violations(path) == [], f"{name} is allowlisted but still reported violations"


def test_the_sync_guard_named_in_the_allowlist_comment_exists() -> None:
    """The justification must point at the guard that actually enforces it.

    The first version of this allowlist cited `check_test_inventory_group_vars.py`,
    which only runs `ansible-inventory --list` and asserts one key resolves — it
    performs no comparison. The real enforcer is `check_role_facts_synced.py`.
    A load-bearing comment naming the wrong script sends the next reader to the
    wrong place, so the name is pinned here.
    """
    repo = Path(__file__).resolve().parents[2]
    enforcer = repo / "autobot-slm-backend/ansible/tests/check_role_facts_synced.py"
    assert enforcer.is_file(), "the sync guard cited by the allowlist comment does not exist"

    source = Path(__file__).with_name("check_canonical_role_names.py").read_text(encoding="utf-8")
    assert "check_role_facts_synced.py" in source, "the allowlist comment must name the real enforcer"


def test_a_negated_membership_check_is_also_blocked() -> None:
    """`'X' not in node_roles` is the same deprecated gate, inverted."""
    body = "when: \"'backend' not in node_roles\"\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "negated.yml", body)
        assert len(find_violations(f)) == 1


def test_the_test_inventory_is_allowlisted() -> None:
    """The test inventory carries the same OR-chains on purpose (#14149).

    Not byte-identical to either sibling — the three files are 411 / 101 / 100
    lines. What `check_role_facts_synced.py` compares is the extracted
    `role_*_active:` fragment, and editing it here would break that comparison
    against the two files already allowlisted.
    """
    assert "autobot-slm-backend/ansible/tests/inventory/group_vars/all.yml" in ALLOWLIST
    assert "autobot-slm-backend/ansible/inventory/group_vars/all.yml" in ALLOWLIST
