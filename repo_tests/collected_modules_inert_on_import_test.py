# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A module pytest may import must not exit the interpreter (#14917).

``autobot-infrastructure/shared/scripts/test_alertmanager.py`` printed a status
summary at module scope and finished with a bare ``sys.exit(0)``. It matches
``python_files = test_*.py``, so pointing pytest at the directory that holds it
did not produce a failing test — ``SystemExit`` was raised *inside the
collector*, pytest died with ``INTERNALERROR``, and every other module in that
session went with it. One file blacks out a whole shard, and the report that
comes back is not "1 failure", it is nothing at all.

That is why this is a first-class bug and not a quirk: the blast radius is the
session, and the damage is silence.

Scanning found a **second** module with the identical defect,
``test_grafana_integration.py``, which #14917 did not name. That is the reason
this guard exists rather than a one-line fix: the population was never derived,
so nobody knew how big it was.

What is checked, and what is deliberately allowed:

* **banned** — a call to ``sys.exit`` / ``exit`` / ``quit`` / ``os._exit``, or a
  ``raise SystemExit``, reachable at import time.
* **allowed** — the same call inside a function, or inside an
  ``if __name__ == "__main__":`` block. 46 modules do exactly that and are
  correct: pytest never executes either. A guard that failed them would be
  ignored within a week, and an ignored guard is an absent one.

The file patterns come from ``pytest.ini`` rather than from a literal, so a
project that adds a third ``python_files`` pattern is covered on the day it
does, and the population floor fails loudly if the sweep ever stops matching.
"""

from __future__ import annotations

import ast
import configparser
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTEST_INI = _REPO_ROOT / "pytest.ini"

# Directories pytest itself never descends into, plus the worktree pool: other
# sessions' checkouts are not this branch's subject and must never be read.
_SKIP = {
    ".git",
    ".worktrees",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tox",
}

# Measured on this branch: 1973 modules match, 2 were fatal, 46 are correctly
# guarded. A floor, not an equality — but far enough below the real number that
# a sweep which has silently stopped matching cannot pass by finding nothing.
_MIN_MODULES_SCANNED = 1800
_MIN_GUARDED_EXITS = 30

_EXIT_NAMES = {"exit", "_exit", "quit"}


def _python_file_patterns() -> list[str]:
    """pytest's own ``python_files`` globs, read from the config it will use."""
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read(_PYTEST_INI, encoding="utf-8")
    patterns = parser.get("pytest", "python_files", fallback="").split()
    assert patterns, "pytest.ini declares no python_files — cannot derive the population"
    return patterns


def _matches(path: Path, patterns: list[str]) -> bool:
    return any(path.match(pattern) for pattern in patterns)


def _is_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    source = ast.unparse(node.test)
    return "__name__" in source and "__main__" in source


def _exit_calls(tree: ast.Module, *, guarded: bool) -> list[tuple[str, int]]:
    """Interpreter-killing statements reachable at import time.

    ``guarded=True`` inverts the walk and returns the ones *inside* a
    ``__main__`` block instead, which is what proves the exemption branch is
    live rather than merely written down.
    """
    found: list[tuple[str, int]] = []
    stack: list[ast.AST] = [node for node in tree.body if _is_main_guard(node) is guarded]
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if not guarded and _is_main_guard(node):
            continue
        if isinstance(node, ast.Raise):
            raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(raised, ast.Name) and raised.id == "SystemExit":
                found.append(("raise SystemExit", node.lineno))
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in _EXIT_NAMES:
                found.append((ast.unparse(node)[:60], node.lineno))
        stack.extend(ast.iter_child_nodes(node))
    return found


def _collectable_modules() -> list[Path]:
    patterns = _python_file_patterns()
    return sorted(
        path
        for path in _REPO_ROOT.rglob("*.py")
        if not _SKIP.intersection(path.relative_to(_REPO_ROOT).parts)
        and _matches(path, patterns)
    )


def test_the_population_is_large_enough_for_this_to_mean_anything() -> None:
    """An empty sweep reports a clean tree. Assert the subject is present."""
    modules = _collectable_modules()
    assert len(modules) >= _MIN_MODULES_SCANNED, (
        f"only {len(modules)} modules match pytest's python_files patterns "
        f"({_python_file_patterns()}) — expected at least {_MIN_MODULES_SCANNED}. "
        "The sweep has stopped matching and would report every tree clean."
    )


def test_the_exemption_branch_has_live_subjects() -> None:
    """`__main__`-guarded exits must exist, or the exemption is untested.

    An allowance nothing exercises is an allowance nobody has checked. If this
    ever reaches zero, the walk that skips `__main__` blocks could be doing
    anything at all and every test here would still pass.
    """
    guarded = [
        path
        for path in _collectable_modules()
        if _exit_calls(ast.parse(path.read_text(encoding="utf-8")), guarded=True)
    ]
    assert len(guarded) >= _MIN_GUARDED_EXITS, (
        f"only {len(guarded)} test-named modules exit from inside a __main__ guard "
        f"(expected at least {_MIN_GUARDED_EXITS}) — the exemption is now untested"
    )


def test_no_test_named_module_exits_the_interpreter_at_import_time() -> None:
    """#14917's first acceptance criterion, over the whole repository."""
    offenders = {
        str(path.relative_to(_REPO_ROOT)): _exit_calls(
            ast.parse(path.read_text(encoding="utf-8")), guarded=False
        )
        for path in _collectable_modules()
    }
    offenders = {name: calls for name, calls in offenders.items() if calls}
    detail = "\n".join(
        f"  {name}: " + ", ".join(f"{call} (line {line})" for call, line in calls)
        for name, calls in sorted(offenders.items())
    )
    assert not offenders, (
        f"{len(offenders)} module(s) matching pytest's python_files patterns exit "
        f"the interpreter at import time:\n{detail}\n"
        "pytest imports these during collection, so this is not a failing test — it "
        "is INTERNALERROR: SystemExit, which kills the entire session and every "
        "other module in the shard. Move the body behind a main() function and an "
        "`if __name__ == \"__main__\":` guard, or rename the file out of the "
        "test_* namespace if it is not a test (#14917)."
    )


def test_the_detector_catches_a_planted_exit_and_spares_a_guarded_one() -> None:
    """Self-test: a checker that has stopped detecting reports a false PASS.

    The banned spelling is assembled at runtime so this module does not trip
    its own rule — a fixture quoting a pattern is still an instance of it.
    """
    call = "sys." + "exit" + "(0)"
    fatal = ast.parse("import sys\nprint('hi')\n" + call + "\n")
    assert _exit_calls(fatal, guarded=False), "the detector missed a bare module-level exit"

    inert = ast.parse('import sys\n\n\ndef main():\n    return 0\n\n\nif __name__ == "__main__":\n    ' + call + "\n")
    assert not _exit_calls(inert, guarded=False), (
        "a __main__-guarded exit was reported — that spelling is correct and "
        "flagging it would get this guard disabled"
    )
    assert _exit_calls(inert, guarded=True), "the guarded-exit walk found nothing to exempt"

    nested = ast.parse("import sys\n\n\ndef teardown():\n    " + call + "\n")
    assert not _exit_calls(nested, guarded=False), (
        "an exit inside a function body was reported — pytest never runs it on import"
    )
