# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every module a CI step imports by name must exist in the tree (#14252).

`deployment-check` asked whether the application's core imports resolve, using a
module path that had never existed. It raised ModuleNotFoundError on every run
for months. Nothing could tell: the only thing asserting that string was the job
it broke, and the job is not a required context, so its redness was permanent
background rather than a signal.

A check that cannot pass is indistinguishable from a check that is not there.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"

# `python3 -c '...'` / `python -c "..."` inline programs in workflow steps.
_INLINE_PYTHON = re.compile(r"""python3?\s+-c\s+(['"])(?P<code>.+?)\1""", re.DOTALL)

# Roots the workflows put on PYTHONPATH for those inline programs.
_IMPORT_ROOTS = ("autobot-backend", "autobot_shared", ".")

# Third-party and stdlib names are resolved by the installed environment, not the
# tree, so only first-party roots are checked. A name is first-party if its top
# level exists as a module or package under one of the roots above.
_STDLIB_OR_THIRD_PARTY_PREFIXES = ("os", "sys", "json", "pathlib", "subprocess")


def _inline_programs() -> list[tuple[str, str]]:
    found = []
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for match in _INLINE_PYTHON.finditer(text):
            found.append((workflow.name, match.group("code")))
    return found


def _imported_names(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []  # a shell-interpolated program is not ours to parse
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def _resolves_in_tree(dotted: str) -> bool:
    relative = Path(*dotted.split("."))
    for root in _IMPORT_ROOTS:
        base = _REPO_ROOT / root
        if (base / relative).with_suffix(".py").is_file():
            return True
        if (base / relative / "__init__.py").is_file():
            return True
    return False


def _is_first_party(dotted: str) -> bool:
    """True when the TOP level of the name exists in the tree.

    Keyed on the top level, not the full path: `security.secure_command_executor`
    must count as first-party (so its absence is a failure) precisely because
    `security/` is a real package here. Keying on the full path would classify
    every wrong path as third-party and pass.
    """
    top = dotted.split(".")[0]
    if top in _STDLIB_OR_THIRD_PARTY_PREFIXES:
        return False
    return _resolves_in_tree(top)


def test_the_scan_actually_found_inline_programs():
    """An empty scan would make the assertion below vacuous."""
    programs = _inline_programs()

    assert len(programs) >= 2, f"only {len(programs)} inline python programs found"


@pytest.mark.parametrize("workflow,code", _inline_programs())
def test_every_first_party_import_in_a_workflow_step_resolves(workflow, code):
    missing = [
        name
        for name in _imported_names(code)
        if _is_first_party(name) and not _resolves_in_tree(name)
    ]

    assert missing == [], (
        f"{workflow}: imports a module path that does not exist in the tree: {missing}. "
        "The step will raise ModuleNotFoundError on every run."
    )


def test_the_path_that_was_wrong_would_now_be_caught():
    """The reproduction, as a direct assertion on the classifier.

    `security` is a real package, so the top-level check calls this first-party;
    the full path does not resolve, so it is reported.
    """
    assert _is_first_party("security.secure_command_executor")
    assert not _resolves_in_tree("security.secure_command_executor")


def test_the_corrected_path_resolves():
    assert _resolves_in_tree("secure_command_executor")
    assert _resolves_in_tree("security_layer")
    assert _resolves_in_tree("app_factory")
