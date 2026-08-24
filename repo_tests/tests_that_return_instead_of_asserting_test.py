# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A test that returns a value instead of asserting cannot fail (#14920).

pytest discards whatever a test function returns. A function ending in
``return False`` therefore passes, and so does the same function ending in
``return True`` — the two branches are indistinguishable to the runner. The
function reads like a check, is collected, is counted, and is reported green
whichever way it went. That is worse than an absent test, because an absent
test does not appear in the total.

WHY A CONFIG SETTING IS NOT THE WHOLE FIX
-----------------------------------------
``filterwarnings = error::pytest.PytestReturnNotNoneWarning`` in ``pytest.ini``
does turn the warning into a failure — verified against pytest 9.0.2 — and it
belongs there the moment the collected trees are clean. It is not a substitute
for this file, for two reasons:

* it only ever sees tests that **run**. Of the returns measured on this branch,
  141 of 277 are in trees no pytest invocation collects, so the warning would
  never be emitted for them and the config would report a clean tree while more
  than half the population sat outside its reach.
* it fires per test execution, so a test skipped in a shard, deselected by a
  marker, or living behind a collection error contributes nothing.

An AST sweep has neither limit: it reaches every module on disk whether or not
anything runs it.

HOW A RETURN IS ATTRIBUTED
--------------------------
To the test function that **directly** encloses it. A naive ``ast.walk``
descends into nested helper functions and closures defined inside a test and
counts their returns as the test's own; on this branch that inflates 277 to
1870, a number nearly seven times too large that would make any ratchet
meaningless.

WHAT IS DELIBERATELY NOT COUNTED, AND WHY
-----------------------------------------
Measured on this branch, each derived from the code rather than from a list:

* **121** returns in ``test_*`` methods of classes that do not match
  ``python_classes`` — pytest never collects them, so they are ordinary
  methods that happen to be named like tests. Counting them would demand
  edits that change nothing.
* **11** returns in ``test_*`` functions decorated with ``@pytest.fixture`` —
  a fixture is *supposed* to return; its name is the only thing test-shaped
  about it.
* generator tests (``yield``), whose ``return`` sets StopIteration rather than
  a value pytest would read. There are none today, and the branch is exercised
  by the self-test below rather than left unproven.
* a bare ``return`` and an explicit ``return None`` — pytest does not warn on
  either, because neither returns a value.

THE RATCHET
-----------
Keyed on the top-level tree, never on a filename: an exemption keyed on a path
is stranded by the first rename, and a stranded exemption exempts nothing
while looking authoritative. Every tree not named in ``_KNOWN_OFFENDERS`` is
pinned at **zero** by derivation, so a new offender anywhere in the eleven
clean trees fails on arrival without anyone maintaining a list. The named
trees may only shrink, and an entry that reaches zero must be deleted rather
than left at ``0`` — a budget nobody can spend is still a budget somebody will.
"""

from __future__ import annotations

import ast
import configparser
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTEST_INI = _REPO_ROOT / "pytest.ini"

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

# Measured on this branch, per top-level tree, in RETURN STATEMENTS.
# Ceilings that must only ever fall. Delete an entry when it reaches zero.
# #14926 tracks draining these; every tree absent from this map is pinned at 0.
_KNOWN_OFFENDERS = {
    "autobot-backend": 136,
    "autobot-infrastructure": 134,
    "autobot-npu-worker": 7,
}

# Floors under the population itself. A sweep that has silently stopped
# matching finds no offenders and reads exactly like a clean tree.
_MIN_MODULES = 1800
_MIN_TEST_FUNCTIONS = 25000


def _pytest_option(name: str) -> list[str]:
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read(_PYTEST_INI, encoding="utf-8")
    values = parser.get("pytest", name, fallback="").split()
    assert values, f"pytest.ini declares no {name} — the population cannot be derived"
    return values


def _test_modules() -> list[Path]:
    """Every file pytest's own ``python_files`` globs would consider."""
    patterns = _pytest_option("python_files")
    return sorted(
        path
        for path in _REPO_ROOT.rglob("*.py")
        if not _SKIP.intersection(path.relative_to(_REPO_ROOT).parts)
        and any(path.match(pattern) for pattern in patterns)
    )


def _prefixes() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``python_functions`` and ``python_classes`` as plain name prefixes."""
    functions = tuple(p.rstrip("*") for p in _pytest_option("python_functions"))
    classes = tuple(p.rstrip("*") for p in _pytest_option("python_classes"))
    return functions, classes


def _collectable_tests(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Functions pytest would collect as tests from this module.

    Module-level ``test_*`` functions, and ``test_*`` methods of ``Test*``
    classes. A method of any other class is not collected, so its return value
    is nobody's verdict.
    """
    functions, classes = _prefixes()
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith(classes):
            found.extend(
                child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return [node for node in found if node.name.startswith(functions)]


def _own_nodes(function: ast.AST, wanted: tuple[type, ...]) -> list[ast.AST]:
    """Nodes belonging to ``function`` itself, never to a nested definition."""
    found: list[ast.AST] = []
    stack: list[ast.AST] = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, wanted):
            found.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return found


def _is_fixture(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in function.decorator_list:
        node = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
        if name == "fixture":
            return True
    return False


def offending_returns(source: str) -> list[tuple[str, int]]:
    """``(test name, line)`` for every value-return a collected test makes.

    A plain function over source text, so it can be driven with a synthetic
    module. A detector only ever pointed at the real tree cannot be told apart
    from one that has stopped detecting.
    """
    tree = ast.parse(source)
    found: list[tuple[str, int]] = []
    for function in _collectable_tests(tree):
        if _is_fixture(function) or _own_nodes(function, (ast.Yield, ast.YieldFrom)):
            continue
        for node in _own_nodes(function, (ast.Return,)):
            value = node.value
            if value is None or (isinstance(value, ast.Constant) and value.value is None):
                continue
            found.append((function.name, node.lineno))
    return found


def _offenders_by_tree() -> dict[str, list[str]]:
    counts: dict[str, list[str]] = {}
    for module in _test_modules():
        relative = module.relative_to(_REPO_ROOT)
        for name, line in offending_returns(module.read_text(encoding="utf-8")):
            counts.setdefault(relative.parts[0], []).append(f"{relative}:{line} {name}")
    return counts


def test_the_population_is_present_and_large_enough_to_mean_anything() -> None:
    """Floors on the subject, not on the findings. Zero of zero is not clean."""
    modules = _test_modules()
    assert len(modules) >= _MIN_MODULES, (
        f"only {len(modules)} modules match pytest's python_files "
        f"{_pytest_option('python_files')} — expected at least {_MIN_MODULES}. "
        "The sweep has stopped matching and would call every tree clean."
    )
    total = sum(
        len(_collectable_tests(ast.parse(module.read_text(encoding="utf-8"))))
        for module in modules
    )
    assert total >= _MIN_TEST_FUNCTIONS, (
        f"only {total} collectable test functions found across {len(modules)} modules "
        f"— expected at least {_MIN_TEST_FUNCTIONS}; the collector model has drifted "
        "from pytest's and this guard is looking at the wrong population"
    )


def test_no_tree_outside_the_known_set_has_a_test_that_returns_a_value() -> None:
    """The hard zero. Eleven clean trees, derived — no list to go stale."""
    offenders = _offenders_by_tree()
    surprises = {
        tree: sites for tree, sites in offenders.items() if tree not in _KNOWN_OFFENDERS
    }
    detail = "\n".join(
        f"  {tree}:\n    " + "\n    ".join(sorted(sites))
        for tree, sites in sorted(surprises.items())
    )
    assert not surprises, (
        "these tests return a value instead of asserting, in a tree that was "
        f"clean:\n{detail}\n"
        "pytest discards the value, so the test passes whichever branch it takes. "
        "Use `assert`; if the value is consumed by another test it is a fixture, "
        "and if the function was never a test, move it behind a main() guard "
        "(#14920)."
    )


def test_the_known_offender_budgets_only_ever_shrink() -> None:
    """Ratchet, both directions — a recorded shrink must be locked in (#14498)."""
    offenders = _offenders_by_tree()
    over = {
        tree: (len(offenders.get(tree, [])), budget)
        for tree, budget in _KNOWN_OFFENDERS.items()
        if len(offenders.get(tree, [])) > budget
    }
    assert not over, (
        "these trees gained tests that return a value instead of asserting "
        f"(actual, budget): {over}. The budgets are ceilings, not targets (#14920)."
    )
    drained = sorted(tree for tree in _KNOWN_OFFENDERS if not offenders.get(tree))
    assert not drained, (
        f"{drained} no longer contain any returning test — delete the entry from "
        "_KNOWN_OFFENDERS so the tree is pinned at zero. A budget left behind after "
        "the work is done is spendable, and it will be spent."
    )
    spent = {
        tree: (len(offenders.get(tree, [])), budget)
        for tree, budget in _KNOWN_OFFENDERS.items()
        if len(offenders.get(tree, [])) < budget
    }
    assert not spent, (
        "these trees are now BELOW their recorded budget (actual, budget): "
        f"{spent}. Lower the number here in the same commit, or the lines a fix "
        "removed can be spent back inside a stale tolerance."
    )


def test_the_detector_finds_a_planted_return_and_spares_the_legitimate_ones() -> None:
    """Self-test. Every exclusion branch is exercised, not merely written down."""
    assert offending_returns("def test_a():\n    return False\n") == [("test_a", 2)]
    assert offending_returns("class TestX:\n    def test_a(self):\n        return 1\n")

    # Excluded, and each for a different reason.
    assert not offending_returns("def test_a():\n    return\n"), "a bare return"
    assert not offending_returns("def test_a():\n    return None\n"), "an explicit None"
    assert not offending_returns(
        "import pytest\n\n\n@pytest.fixture\ndef test_a():\n    return 1\n"
    ), "a fixture is supposed to return"
    assert not offending_returns(
        "def test_a():\n    yield 1\n    return 2\n"
    ), "a generator's return is StopIteration's value, not a verdict"
    assert not offending_returns(
        "class Helper:\n    def test_a(self):\n        return 1\n"
    ), "pytest does not collect a method of a non-Test class"

    # Attribution: the nested helper owns its own return, the test does not.
    nested = "def test_a():\n    def helper():\n        return 1\n\n    helper()\n"
    assert not offending_returns(nested), (
        "a nested helper's return was attributed to its enclosing test — that is "
        "the naive walk this guard exists to avoid"
    )
