# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What pytest would collect, and which of a test's assertions can actually fire.

Static model shared by the guards that reason about the collected test
population. Two questions live here, both answered from the AST alone with no
execution:

* **What would pytest collect?** ``test_modules`` applies pytest's own
  ``python_files`` globs as a denylist walk from the repo root, and
  ``collectable_tests`` applies ``python_classes`` / ``python_functions``. The
  options are read out of ``pytest.ini`` rather than restated, so the model
  cannot drift from the runner by anyone editing one and not the other.
* **Can this test fail?** ``propagating_guards`` answers whether an ``assert``
  or ``raise`` in a collected test can actually reach pytest, which is a
  different question from whether one is written down (#15195, below).
* **Does this test run anything?** ``empty_bodies`` answers whether a collected
  test's body is entirely no-ops — ``pass``, ``...``, a docstring, ``print()``
  — which neither of the ceilings driven from here can see, because such a test
  returns no verdict to discard and holds no assertion to discount (#15189,
  below).

Split out of ``tests_that_return_instead_of_asserting_test.py`` when a second
guard needed the same model. Two copies of "what pytest collects" would drift,
and a drifted collection model is the failure this repository has already hit
twice: #14927 matched ``python_classes`` by name and missed every
``unittest.TestCase``, and #15018 enumerated half of nothing and called it
covered. Same reason ``uncollected_class_model.py`` exists next door.

This module holds no ratchet and no budget. The numbers live with the guards
that enforce them.

WHEN AN ASSERT DOES NOT COUNT AS PROTECTION (#15195)
----------------------------------------------------
A test that asserts as well as returns is exempt, because it can still fail.
That held only while an ``assert`` which is PRESENT was an ``assert`` which can
FIRE, and for one very common shape it is not::

    def test_thing():
        try:
            assert cache.get("k") == "v"
            return True
        except Exception:
            return False

``except Exception`` catches ``AssertionError``. The assertion is inert, the
function returns on both branches, and the test cannot fail whichever way it
goes — while reading as defended to a sweep that only looked for the node. Nine
of the ten functions in #15189 were exactly this, and this guard passed over
every one of them for as long as the file existed.

So the exemption is now spent only on assertions that can reach pytest. An
``assert`` or ``raise`` is discounted when it sits in the ``try`` body of a
``try`` whose handler catches ``Exception``, ``BaseException`` or
``AssertionError`` and neither re-raises nor calls a pytest outcome
(``fail``/``exit``/``skip``/``xfail``). The rule is deliberately narrow in three
directions, because a guard that over-flags is a guard somebody switches off:

* a handler naming a specific non-assertion exception (``except ValueError``)
  protects nothing away and is not counted;
* ``else`` and ``finally`` clauses, and the handler bodies themselves, are not
  covered by that try's own handlers, so assertions there stay live;
* the ownership rule is unchanged — a nested helper's swallow is the helper's.

The same machinery drives ``_SWALLOWED_ASSERTIONS``, a second down-only ceiling
covering the general form: an inert assertion in a test that does NOT return a
value. The ceiling on returns cannot see those, and there are nine of them.
"""

from __future__ import annotations

import ast
import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTEST_INI = REPO_ROOT / "pytest.ini"

SKIP = {
    ".git",
    ".worktrees",
    # Harness territory: tooling config plus the agent worktrees checked out
    # under it, which hold other branches' work in progress and are not always
    # parseable. pytest's own testpaths never reach it either, so nothing here
    # is collectable and nothing here is this sweep's subject.
    ".claude",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tox",
}

def pytest_option(name: str) -> list[str]:
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read(PYTEST_INI, encoding="utf-8")
    values = parser.get("pytest", name, fallback="").split()
    assert values, f"pytest.ini declares no {name} — the population cannot be derived"
    return values


def parse_module(path: Path) -> ast.Module:
    """Parse one swept file, failing loudly and by name if it cannot be parsed.

    This sweep is a denylist walk from the repo root, filtered only by ``SKIP``,
    so it reaches files pytest's ``testpaths`` allowlist never would: scratch
    copies, templates, half-written drafts. An unparseable one must never read as
    "clean" -- skipping it silently is the exact under-reporting failure this
    guard exists to catch -- so it is raised as a failure that names the file and
    says how to take it out of the sweep on purpose.
    """
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        relative = path.relative_to(REPO_ROOT)
        raise AssertionError(
            f"{relative}:{exc.lineno or 0} is not parseable Python ({exc.msg}). "
            "This guard sweeps every *.py under the repo root as a denylist, so it "
            "sees files pytest's own testpaths allowlist never reaches. Fix the "
            "file, or -- if it is scratch, vendored or another branch's work and "
            "does not belong in the sweep -- add its top-level directory to SKIP "
            "in every repo_tests guard that sweeps, the way .claude and .worktrees "
            "already are. Do not silence this by skipping the file: a file the "
            "sweep cannot read is not a file the sweep has cleared."
        ) from exc


def test_modules() -> list[Path]:
    """Every file pytest's own ``python_files`` globs would consider."""
    patterns = pytest_option("python_files")
    return sorted(
        path
        for path in REPO_ROOT.rglob("*.py")
        if not SKIP.intersection(path.relative_to(REPO_ROOT).parts)
        and any(path.match(pattern) for pattern in patterns)
    )


def prefixes() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``python_functions`` and ``python_classes`` as plain name prefixes."""
    functions = tuple(p.rstrip("*") for p in pytest_option("python_functions"))
    classes = tuple(p.rstrip("*") for p in pytest_option("python_classes"))
    return functions, classes


def collectable_tests(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Functions pytest would collect as tests from this module.

    Module-level ``test_*`` functions, and ``test_*`` methods of ``Test*``
    classes. A method of any other class is not collected, so its return value
    is nobody's verdict.

    A method carries its enclosing class's decorators on ``class_decorator_list``
    (empty for a module-level function), because the AST gives no parent
    pointer and ``is_declared_not_running`` needs to see a class-level
    ``@pytest.mark.skip`` that the method itself never spells out (#15263).
    """
    functions, classes = prefixes()
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.class_decorator_list = []  # type: ignore[attr-defined]
            found.append(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith(classes):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    child.class_decorator_list = node.decorator_list  # type: ignore[attr-defined]
                    found.append(child)
    return [node for node in found if node.name.startswith(functions)]


def own_nodes(function: ast.AST, wanted: tuple[type, ...]) -> list[ast.AST]:
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


# ---------------------------------------------------------------------------
# Is an assertion able to fire? (#15195)
#
# The exemption below spares a test that asserts AND returns, on the reasoning
# that such a test can still fail. That reasoning assumes an ``assert`` which is
# PRESENT is an ``assert`` which can FIRE. Under a handler that catches
# ``AssertionError``, it cannot: the assertion is inert, the test cannot fail
# whichever way it goes, and the sweep built to find tests that cannot fail read
# it as defended. Nine of the ten functions in #15189 had exactly this shape.
#
# So an assertion is counted as protective only when nothing lexically between
# it and the function boundary would catch what it raises.
# ---------------------------------------------------------------------------

# Handlers that catch an AssertionError: a bare ``except:``, and any handler
# naming one of these. ``Exception`` is the one that does the damage in
# practice, because it is the one people write without meaning to catch a
# failed assertion.
ASSERTION_CATCHING = frozenset({"Exception", "BaseException", "AssertionError"})

# A handler that catches the assertion but turns it back into a verdict is NOT
# swallowing it. ``raise`` re-raises, an ``assert`` in the handler re-checks,
# and pytest's outcome calls end the test rather than let it report green.
# ``skip``/``xfail`` are in the set deliberately: a skipped test is not a
# passing test, and a guard that over-flags is a guard somebody switches off —
# which would be worse than the blindness this rule removes.
OUTCOME_CALLS = frozenset({"fail", "exit", "skip", "xfail"})

TRY_NODES: tuple[type, ...] = (
    (ast.Try, ast.TryStar) if hasattr(ast, "TryStar") else (ast.Try,)
)


def catches_an_assertion(handler: ast.ExceptHandler) -> bool:
    """Would this handler catch an ``AssertionError`` raised in the try body?"""
    if handler.type is None:
        return True
    named = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for node in named:
        name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
        if name in ASSERTION_CATCHING:
            return True
    return False


def reports_the_failure(handler: ast.ExceptHandler) -> bool:
    """Does the handler hand the failure back on, rather than absorb it?"""
    for node in own_nodes(handler, (ast.Raise, ast.Assert, ast.Call)):
        if isinstance(node, (ast.Raise, ast.Assert)):
            return True
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in OUTCOME_CALLS:
            return True
    return False


def swallows_assertions(node: ast.AST) -> bool:
    """True when this ``try`` neutralises assertions made in its own body."""
    return any(
        catches_an_assertion(handler) and not reports_the_failure(handler)
        for handler in getattr(node, "handlers", ())
    )


def collect_guards(node: ast.AST, swallowed: bool, found: list[ast.AST]) -> None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return
    if isinstance(node, (ast.Assert, ast.Raise)):
        if not swallowed:
            found.append(node)
        return
    if isinstance(node, TRY_NODES):
        inside = swallowed or swallows_assertions(node)
        for child in node.body:
            collect_guards(child, inside, found)
        # ``else``, ``finally`` and the handler bodies are NOT covered by this
        # try's own handlers — anything raised there propagates — so they keep
        # whatever protection state the enclosing scope had.
        for child in (*node.handlers, *node.orelse, *node.finalbody):
            collect_guards(child, swallowed, found)
        return
    for child in ast.iter_child_nodes(node):
        collect_guards(child, swallowed, found)


def propagating_guards(function: ast.AST) -> list[ast.AST]:
    """``assert``/``raise`` owned by ``function`` that can actually reach pytest.

    Same ownership rule as ``_own_nodes``: a nested definition owns its own.
    """
    found: list[ast.AST] = []
    for child in ast.iter_child_nodes(function):
        collect_guards(child, False, found)
    return found


def is_fixture(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in function.decorator_list:
        node = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
        if name == "fixture":
            return True
    return False


def swallowed_assertions(source: str) -> list[tuple[str, int]]:
    """``(test name, line)`` for every test holding an assertion that cannot fire.

    The general form of the #15195 defect, independent of whether the function
    also returns a value. Driven from source text for the same reason
    ``offending_returns`` is: a detector only ever pointed at the live tree
    cannot be distinguished from one that has stopped detecting.
    """
    return swallowed_assertions_in(ast.parse(source))


def swallowed_assertions_in(tree: ast.Module) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for function in collectable_tests(tree):
        if is_fixture(function):
            continue
        live = {id(node) for node in propagating_guards(function)}
        inert = [
            node
            for node in own_nodes(function, (ast.Assert,))
            if id(node) not in live
        ]
        if inert:
            found.append((function.name, inert[0].lineno))
    return found


def test_functions_by_tree() -> dict[str, int]:
    """Collectable test functions per top-level tree.

    The presence half of the ratchet: a per-tree count, because the repo-wide
    floors below cannot notice one tree's walk collapsing inside a population
    of 27,000.
    """
    counts: dict[str, int] = {}
    for module in test_modules():
        tree = module.relative_to(REPO_ROOT).parts[0]
        found = collectable_tests(parse_module(module))
        counts[tree] = counts.get(tree, 0) + len(found)
    return counts


# ---------------------------------------------------------------------------
# Does this test execute anything at all? (#15189)
#
# The third shape, and the one neither ceiling above can see. A test with no
# `return` and no `assert` is invisible to both — there is no returned verdict
# to discard and no inert assertion to discount — yet a body of `pass` plus a
# docstring claiming a check is the same defect in its purest form: a green
# tile for work never done. `test_migrated_files_import` in #15189 was exactly
# this, six `print()` calls announcing six successful imports with the `import`
# statements stripped out, and it reported success for all six.
#
# The rule is deliberately the narrowest one that catches it: EVERY statement
# in the body is a no-op. A body that calls anything at all is out of scope,
# because "it does not raise" is a real, if thin, assertion and flagging it
# would make this guard the kind somebody switches off.
# ---------------------------------------------------------------------------

# Decorators that declare the test is not expected to run or not expected to
# pass. An empty body under one of those is honest rather than misleading, so
# it is not this guard's subject.
DECLARED_NOT_RUNNING = frozenset({"skip", "skipif", "xfail"})


def is_declared_not_running(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if the function OR its enclosing ``Test*`` class declares a skip.

    A method under a class-level ``@pytest.mark.skip`` never repeats the
    decorator on itself, but pytest still honours the class's — so a method's
    own ``decorator_list`` alone is not enough (#15263).
    """
    own = function.decorator_list
    inherited = getattr(function, "class_decorator_list", [])
    for decorator in (*own, *inherited):
        node = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
        if name in DECLARED_NOT_RUNNING:
            return True
    return False


def does_nothing(statement: ast.stmt) -> bool:
    """True for a statement that cannot observe, change or check anything.

    ``pass``, ``...``, a bare string (docstring, or a comment written as one)
    and ``print(literal, ...)`` — the four ways a body can be written out in
    full and still run no check. ``print`` is matched only as a bare name: an
    attribute call such as ``reporter.print(...)`` is somebody's method and
    may do work. ``print(subject())`` is not a no-op either: the argument is
    evaluated before ``print`` ever runs, so it is a real call that can raise
    — the same "a call is a real check" principle this module applies
    everywhere else — and only a literal argument leaves nothing evaluated.
    """
    if isinstance(statement, ast.Pass):
        return True
    if not isinstance(statement, ast.Expr):
        return False
    value = statement.value
    if isinstance(value, ast.Constant):
        return True
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "print"
        and not value.keywords
        and all(isinstance(arg, ast.Constant) for arg in value.args)
    )


def empty_bodies(source: str) -> list[tuple[str, int]]:
    """``(test name, line)`` for every collected test that executes nothing.

    Source-driven for the same reason ``swallowed_assertions`` is: a detector
    only ever pointed at the live tree cannot be told apart from one that has
    stopped detecting.
    """
    return empty_bodies_in(ast.parse(source))


def empty_bodies_in(tree: ast.Module) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for function in collectable_tests(tree):
        if is_fixture(function) or is_declared_not_running(function):
            continue
        if all(does_nothing(statement) for statement in function.body):
            found.append((function.name, function.lineno))
    return found
