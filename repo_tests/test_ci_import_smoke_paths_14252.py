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
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"

# `python3 -c '...'` / `python -c "..."` inline programs in workflow steps.
#
# `(?:\\.|(?!\1).)*` rather than `.+?`: a lazy match closes on the first quote
# of the same kind, including a backslash-escaped one, so
# `python -c "import json; print(f\"{x}\")"` was captured truncated. The
# fragment then failed to parse and its imports were checked against nothing.
# Three workflows have that shape.
_INLINE_PYTHON = re.compile(
    r"""python3?\s+-c\s+(['"])(?P<code>(?:\\.|(?!\1).)*)\1""", re.DOTALL
)

# Heredoc form: `python - <<'PY' ... PY`. A separate shape entirely, and one the
# quote-matching pattern above cannot see at all.
_HEREDOC_PYTHON = re.compile(
    r"""python3?\s+-\s*<<-?\s*['"]?(?P<tag>[A-Za-z_][A-Za-z0-9_]*)['"]?\n(?P<code>.*?)\n\s*(?P=tag)\b""",
    re.DOTALL,
)

# Roots the workflows put on PYTHONPATH for those inline programs.
#
# Applied uniformly, not per-step: a step whose own PYTHONPATH omits
# `autobot-backend` is still checked against it. That is deliberate (tracking the
# real PYTHONPATH per step would mean interpreting shell), but it has one known
# failure direction. `autobot-backend/mcp/` is a first-party package AND `mcp` is
# a pip distribution; a future step importing `mcp.<submodule>` that exists in
# the installed package but not in the repo's own would be reported missing here.
# Nothing does that today. If this test ever fails on a name that is genuinely a
# third-party package, that is the case — add it to the list below rather than
# widening the roots.
_IMPORT_ROOTS = ("autobot-backend", "autobot_shared", ".")

# Third-party and stdlib names are resolved by the installed environment, not the
# tree, so only first-party roots are checked. A name is first-party if its top
# level exists as a module or package under one of the roots above.
_STDLIB_OR_THIRD_PARTY_PREFIXES = ("os", "sys", "json", "pathlib", "subprocess")


def _normalise(code: str) -> str:
    """Strip the YAML block indentation a multi-line `-c` argument carries.

    A program written across several lines inside a workflow step arrives with
    the step's indentation on every line, so `ast.parse` raises IndentationError
    — a SyntaxError subclass, indistinguishable from "not python" to a bare
    except. `verify-generated-types.yml:216` is exactly this.
    """
    return textwrap.dedent(code.strip("\n") + "\n")


def _unescape_shell(code: str) -> str:
    """Undo the backslash escaping a double-quoted shell argument requires.

    `\\"` reaches python as `"`. Left in place, every such program is a syntax
    error and its imports go unchecked.
    """
    return code.replace('\\"', '"').replace("\\$", "$").replace("\\`", "`")


def _inline_programs() -> list[tuple[str, str]]:
    found = []
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for match in _INLINE_PYTHON.finditer(text):
            found.append((workflow.name, _normalise(_unescape_shell(match.group("code")))))
        for match in _HEREDOC_PYTHON.finditer(text):
            found.append((workflow.name, _normalise(match.group("code"))))
    return found


def _parses(code: str) -> bool:
    try:
        ast.parse(code)
    except SyntaxError:
        return False
    return True


def _imported_names(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Reported by test_every_extracted_program_parses, never swallowed here.
        # Returning [] quietly is how a guard reports clean on input it could not
        # read -- the same failure this whole file exists to catch, one layer
        # earlier, at extraction instead of classification.
        return []
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


def test_every_extracted_program_parses():
    """A program the extractor mangles is checked against nothing.

    `_INLINE_PYTHON` uses a backreference to close on the same quote it opened
    with, and has no escape-awareness: `python -c "...\\"...\\"..."` closes on the
    first escaped quote and captures a truncated fragment. `ast.parse` then
    raises, `_imported_names` returns [], and the step passes without a single
    import being checked. `coverage.yml` contains exactly that shape.

    Failing loudly here is the point: the guard must be able to say "I could not
    read this", which is different from "this is fine".
    """
    unparseable = [
        (workflow, code[:60]) for workflow, code in _inline_programs() if not _parses(code)
    ]

    assert unparseable == [], (
        "inline python that the extractor could not parse — its imports are "
        f"checked against nothing: {unparseable}"
    )
