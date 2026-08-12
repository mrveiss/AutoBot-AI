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


def test_the_byte_identical_test_inventory_is_allowlisted() -> None:
    """The test inventory duplicates group_vars/all.yml on purpose (#14149).

    It is a real file rather than a symlink because `core.symlinks=false`
    materializes symlinks as plain text, and CI enforces byte-identity with
    the file already allowlisted. "Fixing" its OR-chains would break that
    check, so it is exempt for the same reason the original is.
    """
    assert "autobot-slm-backend/ansible/tests/inventory/group_vars/all.yml" in ALLOWLIST
    assert "autobot-slm-backend/ansible/inventory/group_vars/all.yml" in ALLOWLIST
