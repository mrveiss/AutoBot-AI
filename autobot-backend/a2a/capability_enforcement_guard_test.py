# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every A2A capability has an enforcement site, so a trust level that denies it denies something (#16957).

Three of four capabilities were granted by trust level and checked nowhere. Anyone
reading the matrix concluded that a control existed. This fails the moment a member
exists with no production code that names it outside its own definition.
"""

import ast
import os
from pathlib import Path

from a2a.trust_score import Capability

_BACKEND = Path(__file__).resolve().parents[1]
_DEFINITION = _BACKEND / "a2a" / "trust_score.py"


def _members_named(source: str) -> set:
    """``Capability.<NAME>`` attribute references in *source*."""
    return {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "Capability"
    }


def _is_test_file(name: str) -> bool:
    """pytest.ini's ``python_files`` naming, not a substring: ``"test" in name`` would skip ``attestation.py``."""
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def test_a_production_module_whose_name_contains_test_is_still_scanned():
    """Negative control for the filter: on this tree the old substring match skipped two real modules."""
    assert not _is_test_file("attestation.py") and not _is_test_file("testing_coverage_analyzer.py")
    assert _is_test_file("capability_enforcement_guard_test.py")


def _production_modules():
    """Non-test modules under autobot-backend. ``os.walk`` does not follow the ``backend -> .`` symlink."""
    for root, dirs, files in os.walk(_BACKEND):
        dirs[:] = [d for d in dirs if d not in {"tests", "node_modules", "__pycache__"}]
        for name in files:
            path = Path(root) / name
            if name.endswith(".py") and not _is_test_file(name) and path != _DEFINITION:
                yield path


def test_every_capability_is_enforced_somewhere():
    named = set()
    for path in _production_modules():
        named |= _members_named(path.read_text(encoding="utf-8", errors="replace"))

    unenforced = sorted(c.name for c in Capability if c.name not in named)

    assert not unenforced, f"capabilities no production code enforces -- enforce them or remove them: {unenforced}"


def test_the_scan_sees_a_reference():
    """Negative control: the predicate must find the shape it guards, and nothing else."""
    assert _members_named("require_capability(peer, Capability.SUBMIT_TASKS)") == {"SUBMIT_TASKS"}
    assert _members_named("x = Other.SUBMIT_TASKS") == set()
