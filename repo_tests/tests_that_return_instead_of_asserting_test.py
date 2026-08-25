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
  than half the population sat outside its reach. #14928 covers the related
  hazard: ``pytest`` is unpinned, so the flip arrives on a release nobody chose.
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

* returns in ``test_*`` methods of classes pytest does not collect — they are
  ordinary methods that happen to be named like tests, so converting their
  ``return`` to ``assert`` would change nothing until something runs them. That
  is its own defect, tracked by **#14927** and guarded by
  ``repo_tests/test_methods_in_uncollected_classes_test.py``.

  This exclusion used to be described here as "152 returns in classes that do
  not match ``python_classes``", citing #14927's figure of 120 methods in 23
  classes including 13 in an IDOR hotfix suite. That description was wrong, and
  wrong in a way worth recording: ``python_classes`` is only one of pytest's
  three collection rules. ``unittest.TestCase`` subclasses are collected
  whatever they are called — which is why all 13 of the IDOR tests were
  collecting, running and passing the entire time — and a base class is
  collected through any ``Test*`` subclass that inherits it. Pulling the other
  way, a class WITH ``__init__`` is not collected however it is named, which hid
  41 further methods that neither #14927 nor this file could see. The corrected
  figure was settled by running ``--collect-only``, not by matching names.
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
is stranded by the first rename, and a stranded exemption exempts nothing while
looking authoritative. Every tree not named in ``_KNOWN_OFFENDERS`` is pinned at
**zero** by derivation, so a new offender anywhere in the eleven clean trees
fails on arrival without anyone maintaining a list. The named trees may only
shrink, and an entry that reaches zero must be deleted rather than left at
``0`` — a budget nobody can spend is still a budget somebody will.

Two properties the ratchet has to get right, both of which have bitten this
repository's other baseline guards:

* **a broken scan must not read as progress.** Each named tree carries a floor
  on its own test-function population as well as a ceiling on its offenders. A
  walk that quietly stops matching collapses the offender count to zero, which
  is indistinguishable from finished work — so the collapse is checked first,
  and it fails telling the reader to fix the sweep rather than to write the
  zero down.
* **there is no sanctioned route to raise a number, on purpose.** A test that
  returns a value instead of asserting is never the right thing to write, so no
  reviewer override is offered and none is implied. #14919 exists because a
  guard promised a route its code never implemented; this one promises nothing
  it does not do.
"""

from __future__ import annotations

import ast
import configparser
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTEST_INI = _REPO_ROOT / "pytest.ini"

_SKIP = {
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

# Measured on this branch, per top-level tree:
#   tree: (return statements that must not be exceeded,
#          test functions that must STILL be found in that tree)
#
# The second number is not decoration. Without it, a walk that breaks and
# returns nothing looks identical to a tree somebody finished draining, and the
# ratchet would record the collapse as a triumph and lock it in. A tree may
# only be declared drained while its own population is still demonstrably
# there. Delete an entry once its budget genuinely reaches zero.
_KNOWN_OFFENDERS = {
    # Lowered in the same commit that changed the definition, as this file's own
    # ratchet requires: 136 -> 78 and 134 -> 126.
    #
    # Be precise about WHY these moved, because the obvious reading is wrong.
    # The drop is NOT the nine driver-consumed functions that commit fixed —
    # none of those are in `autobot-backend`, yet that tree fell 58. The whole
    # movement is a side effect of the exemption in `offending_returns`: a test
    # that asserts AND returns is no longer counted, because it can fail and its
    # return value is a separate driver contract (#14920). That tree-wide change
    # un-flags 39 pre-existing functions in `autobot-backend` and 4 in
    # `autobot-infrastructure` that neither commit touched.
    #
    # Those 43 were checked rather than assumed: every one carries real
    # assertions (1-24 apiece) alongside its return, so none is a vacuous assert
    # masking a test that cannot fail.
    #
    # The drop is not a sweep collapse — the population floors below are
    # untouched and still pass, which is what tells the two apart.
    # 78 -> 75 with #14941 (test_celery_worker_status stopped returning a verdict
    # pytest discards) and #14927 (three classes converted to collect, which moves
    # their methods into this file's population as well).
    #
    # 126 -> 121 with #14518: the inline-python and driver scripts under
    # `shared/scripts` (test_phase5_cleanup, verify_backend_config,
    # verify_ssh_manager, test_redis_comparison) now assert instead of handing a
    # verdict back to a caller that discards it. Measured, not estimated — the
    # sweep reports 121 and the population floor below is unmoved, which is what
    # separates a real drain from a sweep that stopped matching.
    "autobot-backend": (75, 18000),
    "autobot-infrastructure": (121, 250),
    "autobot-npu-worker": (7, 150),
}

# Floors under the whole population. A sweep that has silently stopped matching
# finds no offenders and reads exactly like a clean tree.
_MIN_MODULES = 1800
_MIN_TEST_FUNCTIONS = 25000


def _pytest_option(name: str) -> list[str]:
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read(_PYTEST_INI, encoding="utf-8")
    values = parser.get("pytest", name, fallback="").split()
    assert values, f"pytest.ini declares no {name} — the population cannot be derived"
    return values


def _parse_module(path: Path) -> ast.Module:
    """Parse one swept file, failing loudly and by name if it cannot be parsed.

    This sweep is a denylist walk from the repo root, filtered only by ``_SKIP``,
    so it reaches files pytest's ``testpaths`` allowlist never would: scratch
    copies, templates, half-written drafts. An unparseable one must never read as
    "clean" -- skipping it silently is the exact under-reporting failure this
    guard exists to catch -- so it is raised as a failure that names the file and
    says how to take it out of the sweep on purpose.
    """
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        relative = path.relative_to(_REPO_ROOT)
        raise AssertionError(
            f"{relative}:{exc.lineno or 0} is not parseable Python ({exc.msg}). "
            "This guard sweeps every *.py under the repo root as a denylist, so it "
            "sees files pytest's own testpaths allowlist never reaches. Fix the "
            "file, or -- if it is scratch, vendored or another branch's work and "
            "does not belong in the sweep -- add its top-level directory to _SKIP "
            "in every repo_tests guard that sweeps, the way .claude and .worktrees "
            "already are. Do not silence this by skipping the file: a file the "
            "sweep cannot read is not a file the sweep has cleared."
        ) from exc


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
    return _offending_returns(ast.parse(source))


def _offending_returns(tree: ast.Module) -> list[tuple[str, int]]:
    """The tree-driven half, so the repo sweep parses each module once."""
    found: list[tuple[str, int]] = []
    for function in _collectable_tests(tree):
        if _is_fixture(function) or _own_nodes(function, (ast.Yield, ast.YieldFrom)):
            continue
        # The defect is returning *instead of* asserting — a test that cannot fail.
        # A test that asserts AND returns can fail, and its return value is a
        # separate contract: several drivers in this repo sum truthiness over
        # `result = test_func()`, so a bare assert there leaves a passing test
        # counted as failed. Both are needed, and neither is an offence (#14920).
        if _own_nodes(function, (ast.Assert, ast.Raise)):
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
        for name, line in _offending_returns(_parse_module(module)):
            counts.setdefault(relative.parts[0], []).append(f"{relative}:{line} {name}")
    return counts


def _test_functions_by_tree() -> dict[str, int]:
    """Collectable test functions per top-level tree.

    The presence half of the ratchet: a per-tree count, because the repo-wide
    floors below cannot notice one tree's walk collapsing inside a population
    of 27,000.
    """
    counts: dict[str, int] = {}
    for module in _test_modules():
        tree = module.relative_to(_REPO_ROOT).parts[0]
        found = _collectable_tests(_parse_module(module))
        counts[tree] = counts.get(tree, 0) + len(found)
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
        len(_collectable_tests(_parse_module(module)))
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
    """Ratchet, both directions — a recorded shrink must be locked in (#14498).

    THERE IS NO SANCTIONED ROUTE FOR AN INCREASE, and that is deliberate rather
    than an omission. A new test that returns a value instead of asserting is
    never the right thing to write: the value cannot reach pytest, so there is
    nothing an author could be trying to express that ``assert`` does not
    express better. If the value is consumed by another test the function is a
    fixture, and if the function was never a test it belongs behind a
    ``main()`` guard. Raising a number here is not a reviewer decision this
    guard offers — #14919 was filed because a guard advertised a route its code
    did not implement, so this one advertises none.

    Lowering a number, by contrast, needs no permission at all: fix a test and
    the assertion below tells you the new figure to write down.
    """
    offenders = _offenders_by_tree()
    populations = _test_functions_by_tree()

    collapsed = {
        tree: (populations.get(tree, 0), floor)
        for tree, (_, floor) in _KNOWN_OFFENDERS.items()
        if populations.get(tree, 0) < floor
    }
    assert not collapsed, (
        "the sweep no longer finds the tests it is supposed to be scanning "
        f"(found, floor): {collapsed}. Every count below is therefore untrusted — "
        "a scan that finds nothing reports a clean tree and a drop to zero reads "
        "as progress. Fix the sweep; do NOT lower these numbers to match it."
    )

    over = {
        tree: (len(offenders.get(tree, [])), budget)
        for tree, (budget, _) in _KNOWN_OFFENDERS.items()
        if len(offenders.get(tree, [])) > budget
    }
    assert not over, (
        "these trees gained tests that return a value instead of asserting "
        f"(actual, budget): {over}. The budgets are ceilings and there is no "
        "route to raise one — use `assert` (#14920)."
    )
    drained = sorted(tree for tree, _ in _KNOWN_OFFENDERS.items() if not offenders.get(tree))
    assert not drained, (
        f"{drained} no longer contain any returning test — delete the entry from "
        "_KNOWN_OFFENDERS so the tree is pinned at zero by derivation. A budget "
        "left behind after the work is done is spendable, and it will be spent."
    )
    spent = {
        tree: (len(offenders.get(tree, [])), budget)
        for tree, (budget, _) in _KNOWN_OFFENDERS.items()
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

    # The assert/raise exemption added with the #14920 driver fix. Every other
    # branch here has a synthetic case; without one this branch is proven only
    # by whatever the live tree happens to contain today.
    assert not offending_returns(
        "def test_a():\n    assert True\n    return True\n"
    ), "a test that asserts AND returns can fail; its return is a separate driver contract"
    assert not offending_returns(
        "def test_b():\n    raise AssertionError('x')\n    return True\n"
    ), "a raising test can fail; its return is a separate driver contract"
    assert offending_returns(
        "def test_c():\n    return True\n"
    ), "a test whose return is its ONLY verdict is still an offence"


def test_an_unparseable_swept_file_fails_loudly_instead_of_reading_as_clean() -> None:
    """The sweep is a denylist from the repo root, so it meets stray files.

    One must never be skipped: a file the walk could not read is not a file the
    walk cleared, and dropping it silently is the under-reporting this guard
    exists to catch. It has to fail, name the file and say what to do about it.

    The probe is written under a ``_SKIP``ped directory so no concurrently
    running sweep can pick it up while it exists.
    """
    scratch = _REPO_ROOT / "__pycache__"
    scratch.mkdir(exist_ok=True)
    stray = scratch / "unparseable_probe_test.py"
    stray.write_text("from a-b.c import (\n", encoding="utf-8")
    try:
        with pytest.raises(AssertionError) as raised:
            _parse_module(stray)
    finally:
        stray.unlink()

    message = str(raised.value)
    assert "unparseable_probe_test.py" in message, "the failure must name the file"
    assert "_SKIP" in message, "the failure must say how to exclude a file on purpose"
