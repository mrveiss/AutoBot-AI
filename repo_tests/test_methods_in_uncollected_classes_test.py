# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A ``test_*`` method in a class pytest will not collect never runs (#14927).

This is a strictly worse defect than the one #14920 drains. A test that returns
instead of asserting is at least *counted*: it appears in the total, it has a
node id, and a reader who looks for it finds it. A method in an uncollected
class contributes nothing at all. The file is named ``*_test.py``, it sits in a
collected tree, it imports cleanly, and every signal a reader has says the
tests ran. ``security_idor_hotfix_test.py`` was believed for weeks to be in
this state.

WHY AN AST SWEEP MUST MODEL PYTEST, NOT ``python_classes``
----------------------------------------------------------
#14927 measured this population by matching class names against
``python_classes = Test*`` and reported 120 methods in 23 classes. Checked by
actually collecting the files, 30 of those 120 were false and 41 real ones were
missing. ``python_classes`` is only one of three rules pytest applies, and the
other two run in opposite directions:

* **``unittest.TestCase`` subclasses are collected whatever their name.** pytest
  hands them to its unittest integration, which does not consult
  ``python_classes`` at all. 23 of the 120 are ``TestCase`` subclasses -- among
  them all 13 in ``security_idor_hotfix_test.py``, the case #14927 called its
  sharpest. They collect, they run, and they pass.
* **A base class contributes its methods through any collected subclass.**
  ``ReadOnlyCapabilityChecks`` matches nothing, but ``TestReadOnlyContract`` and
  ``TestDispatchReadOnlyContract`` both inherit it, so its five methods collect
  twice each.
* **A class with ``__init__`` is NOT collected, however it is named.** pytest
  emits ``PytestCollectionWarning`` and moves on. This is the direction that
  actually bites, because the class is *called* ``Test*`` and looks correct:
  five such classes held 41 methods that ran nowhere, and #14927 never counted
  them because it filtered on the name. pytest's own test is
  ``cls.__init__ is not object.__init__``, which walks the whole MRO -- so an
  ``__init__`` reached through a plain base, in this module or one it imports,
  blocks collection exactly as an own one does (#14984). A base this model
  cannot locate is read as carrying ``__init__`` and named outright by
  ``test_no_test_class_inherits_init_from_an_unresolvable_base``, because
  assuming an unreadable base clean is the under-reporting everything here
  exists to prevent.

So the model below is checked against pytest itself, in
``test_the_model_agrees_with_pytest_on_every_shape``, by running a real
``--collect-only`` over a module carrying one of every shape. A model of a
collector is worthless if nothing ever compares it to the collector.

WHAT IS DELIBERATELY NOT COUNTED
--------------------------------
A private stand-in implementing a production interface that happens to declare
a ``test_*`` method. ``AbstractConnector.test_connection`` is such an interface:
``_MinimalConnector`` and ``_DummyConnector`` must implement it under that
name, and renaming it is not available. They are not tests and pytest is right
not to collect them. The exemption is pinned at its exact measured size below
rather than left open, so a third one cannot arrive unnoticed.

THE RATCHET
-----------
Keyed on the top-level tree, never on a filename -- an exemption keyed on a path
is stranded by the first rename, and a stranded exemption exempts nothing while
looking authoritative. Every tree not named in ``_KNOWN_OFFENDERS`` is pinned at
zero by derivation. The named trees may only shrink, and an entry reaching zero
must be deleted rather than left at ``0``.

The population floors are the half that matters most. A sweep that quietly stops
matching finds no offenders, and "no offenders" is indistinguishable from
finished work -- so the collapse is checked *first*, and it fails telling the
reader to fix the sweep rather than to write the zero down.
"""

from __future__ import annotations

import ast
import configparser
import functools
import subprocess
import sys
import textwrap
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
#   tree: (uncollected test_* methods that must not be exceeded,
#          collectable test functions that must STILL be found in that tree)
#
# The second number is not decoration. Without it, a walk that breaks and finds
# nothing looks identical to a tree somebody finished draining, and this file
# would record the collapse as a triumph and lock it in.
#
# Nearly every remaining offender is a live-service validation driver: a class
# with `__init__`, a `run_all_*` loop and a `main()`, whose methods dial a
# running backend and return bool. A bare rename is actively harmful -- a
# `Test*` class keeping its `__init__` collects zero while looking fixed -- so
# they are filed with per-file counts, and this ceiling stops the population
# growing back. "Nearly": #14979 found two that dialled nothing at all.
_KNOWN_OFFENDERS = {
    # 59, not 61: the two interface stubs below are exempt and counted separately.
    # 77 -> 59 (#14979): takeover_manager_e2e_test.py, temporal_invalidation_test.py
    "autobot-backend": (59, 18000),
    # The floor equals the ceiling here, and legitimately so: this tree holds one
    # test module whose single class is uncollected, so every test-shaped thing in
    # it is also an offender. Collecting them moves the ceiling to 0 and leaves the
    # floor at 10, which is exactly the shape a real fix has.
    "autobot-frontend": (10, 10),
    "autobot-infrastructure": (19, 250),
}

# Floors under the whole population, for the same reason as the per-tree ones.
_MIN_MODULES = 1800
_MIN_TEST_FUNCTIONS = 25000

# Private stand-ins implementing a production interface that declares a `test_*`
# method. Pinned at the exact measured count: the exemption is a convention rule
# ("a leading underscore means a helper"), and a convention rule with no ceiling
# is a bypass waiting to be used.
_INTERFACE_STUBS = 2


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
    functions = tuple(p.rstrip("*") for p in _pytest_option("python_functions"))
    classes = tuple(p.rstrip("*") for p in _pytest_option("python_classes"))
    return functions, classes


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return "?"


# The roots pytest itself imports through, so a base resolved here is the base
# the collector will see. Read from pytest.ini rather than listed, for the same
# reason python_files is (#14984).
_PYTHONPATH_ROOTS = tuple((_REPO_ROOT / entry).resolve() for entry in _pytest_option("pythonpath"))


@functools.lru_cache(maxsize=None)
def _parsed(path: Path) -> ast.Module:
    """One parse per file, however many bases lead back to it."""
    return _parse_module(path)


@functools.lru_cache(maxsize=None)
def _module_classes(path: Path) -> dict[str, ast.ClassDef]:
    """The top-level classes another module defines, keyed by name."""
    return {node.name: node for node in _parsed(path).body if isinstance(node, ast.ClassDef)}


def _module_path(dotted: str, level: int, origin: Path) -> Path | None:
    """The repo file a dotted import names, or None if it is not ours.

    Absolute imports resolve against the roots ``pytest.ini`` puts on
    ``pythonpath``, which is what pytest itself will import through; a relative
    import resolves against its own package, ``level`` directories up.
    """
    if level:
        package = origin.parent
        for _ in range(level - 1):
            package = package.parent
        roots: tuple[Path, ...] = (package,)
    else:
        roots = _PYTHONPATH_ROOTS
    tail = Path(*dotted.split(".")) if dotted else Path()
    for root in roots:
        module = (root / tail).with_suffix(".py")
        if module.is_file():
            return module
        package_init = root / tail / "__init__.py"
        if package_init.is_file():
            return package_init
    return None


def _imported_from(tree: ast.Module, dotted: str, origin: Path) -> Path | None:
    """The file the name at the head of ``dotted`` was imported from."""
    head = dotted.split(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any((alias.asname or alias.name) == head for alias in node.names):
                return _module_path(node.module or "", node.level, origin)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if (alias.asname or alias.name.split(".")[0]) == head:
                    return _module_path(alias.name, 0, origin)
    return None


def _base_init_state(
    dotted: str, classes: dict[str, ast.ClassDef], module: Path | None, seen: frozenset[str]
) -> bool | None:
    """``__init__`` state of one named base — same module first, then imports."""
    if dotted in seen or dotted == "object":
        # ``object`` is the very thing pytest compares against
        # (``cls.__init__ is not object.__init__``), so it contributes nothing.
        return False
    if dotted in classes:
        return _init_state(classes[dotted], classes, module, seen | {dotted})
    if module is None or dotted == "?":
        return None
    source = _imported_from(_parsed(module), dotted, module)
    if source is None:
        return None
    outer = _module_classes(source)
    leaf = dotted.rsplit(".", 1)[-1]
    if leaf not in outer:
        return None
    return _init_state(outer[leaf], outer, source, seen | {dotted})


def _init_state(
    node: ast.ClassDef,
    classes: dict[str, ast.ClassDef],
    module: Path | None = None,
    seen: frozenset[str] = frozenset(),
) -> bool | None:
    """Tri-state ``__init__`` lookup up the MRO: True, False, or None = unknown.

    pytest asks ``cls.__init__ is not object.__init__``, which walks the whole
    MRO, so a ``Test*`` class inheriting ``__init__`` from a plain base is not
    collected however clean its own body looks (#14984).

    ``None`` is the explicit decision this model makes about a base it cannot
    locate — a third-party class, a dynamically built one, a name a star-import
    supplied. It is never treated as clean: ``_has_init`` reads it as
    ``__init__``-present so the class's methods count as offenders, and
    ``test_no_test_class_inherits_init_from_an_unresolvable_base`` names it
    outright, because assuming an unreadable base free of ``__init__`` is the
    under-reporting this whole guard exists to catch.
    """
    if any(
        isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "__init__"
        for child in node.body
    ):
        return True
    unknown = False
    for base in node.bases:
        dotted = _dotted(base)
        # unittest's own constructor is framework machinery, not a blocker --
        # _collected_classes has already decided such a class is collected.
        if dotted.rsplit(".", 1)[-1].endswith("TestCase"):
            continue
        state = _base_init_state(dotted, classes, module, seen)
        if state is True:
            return True
        unknown = unknown or state is None
    return None if unknown else False


def _has_init(
    node: ast.ClassDef, classes: dict[str, ast.ClassDef], module: Path | None = None
) -> bool:
    """Whether pytest would refuse this class for having a constructor.

    An unresolvable base counts as one. See ``_init_state`` for why that
    direction, and not the other, is the safe one.
    """
    return _init_state(node, classes, module) is not False


def _collected_classes(
    classes: dict[str, ast.ClassDef], module: Path | None = None
) -> set[str]:
    """The class names pytest would collect from this module.

    Three rules, applied in pytest's own order of precedence. See the module
    docstring for why each is load-bearing. ``module`` is the file the classes
    came from; given one, the ``__init__`` rule follows bases into the modules
    they are imported from (#14984), which a bare source string cannot.
    """
    _, class_prefixes = _prefixes()

    def is_unittest(node: ast.ClassDef, seen: frozenset[str] = frozenset()) -> bool:
        for base in node.bases:
            dotted = _dotted(base)
            if dotted.rsplit(".", 1)[-1].endswith("TestCase"):
                return True
            if dotted in classes and dotted not in seen:
                if is_unittest(classes[dotted], seen | {dotted}):
                    return True
        return False

    collected = set()
    for name, node in classes.items():
        if is_unittest(node):
            # unittest.TestCase never consults python_classes, and its own
            # __init__ is part of the framework rather than a blocker.
            collected.add(name)
        elif name.startswith(class_prefixes) and not _has_init(node, classes, module):
            collected.add(name)

    # A base of a collected class contributes its methods through the subclass.
    changed = True
    while changed:
        changed = False
        for name in list(collected):
            for base in classes[name].bases:
                dotted = _dotted(base)
                if dotted in classes and dotted not in collected:
                    collected.add(dotted)
                    changed = True
    return collected


def uncollected_test_methods(source: str, module: Path | None = None) -> list[tuple[str, str, int]]:
    """``(class, method, line)`` for every ``test_*`` method pytest cannot reach.

    A plain function over source text, so it can be driven with a synthetic
    module. A detector only ever pointed at the real tree cannot be told apart
    from one that has stopped detecting.

    ``module`` is optional and only widens what can be resolved: with the file
    the source came from, an ``__init__`` inherited from another module in the
    repo is followed rather than guessed (#14984). Without it every imported
    base is unresolvable, and an unresolvable base is read as carrying
    ``__init__`` — see ``_init_state``.
    """
    function_prefixes, _ = _prefixes()
    tree = ast.parse(source)
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    collected = _collected_classes(classes, module)

    found: list[tuple[str, str, int]] = []
    for name, node in classes.items():
        if name in collected or _is_interface_stub(node):
            continue
        found.extend(
            (name, child.name, child.lineno)
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            and child.name.startswith(function_prefixes)
        )
    return found


def _unresolvable_bases(
    node: ast.ClassDef, classes: dict[str, ast.ClassDef], module: Path | None
) -> set[str]:
    """The bases of ``node`` whose ``__init__`` state this model cannot settle."""
    unresolvable = set()
    for base in node.bases:
        dotted = _dotted(base)
        if dotted.rsplit(".", 1)[-1].endswith("TestCase"):
            continue
        if _base_init_state(dotted, classes, module, frozenset()) is None:
            unresolvable.add(dotted)
    return unresolvable


def _unresolved_base_sites(parsed: ast.Module, relative: Path, module: Path) -> list[str]:
    """``file:line Class(bases)`` for every Test* class with an opaque base."""
    _, class_prefixes = _prefixes()
    classes = {node.name: node for node in parsed.body if isinstance(node, ast.ClassDef)}
    sites = []
    for name, node in classes.items():
        if not name.startswith(class_prefixes):
            continue
        opaque = _unresolvable_bases(node, classes, module)
        if opaque:
            sites.append(f"{relative}:{node.lineno} {name}({', '.join(sorted(opaque))})")
    return sites


def _is_interface_stub(node: ast.ClassDef) -> bool:
    """A private stand-in implementing a base class that dictates the name."""
    return node.name.startswith("_") and bool(node.bases)


def _scanned_test_functions(tree: ast.Module) -> int:
    """Everything test-shaped this guard LOOKS AT, collected or not.

    Deliberately not "everything pytest collects". A tree can legitimately hold
    zero collectable tests while holding plenty for this sweep to examine --
    ``autobot-frontend`` is exactly that today, one module whose only class is
    uncollected. A floor on the collected subset would read as a collapsed sweep
    there, and the first person to see it would "fix" it by deleting the floor.
    The invariant that actually matters is that the walk still reaches its
    subject, so the subject is what gets counted.
    """
    function_prefixes, _ = _prefixes()
    total = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total += node.name.startswith(function_prefixes)
        elif isinstance(node, ast.ClassDef):
            total += sum(
                1
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name.startswith(function_prefixes)
            )
    return total


@functools.lru_cache(maxsize=1)
def _scan() -> tuple[dict[str, tuple[str, ...]], dict[str, int], tuple[str, ...], tuple[str, ...]]:
    """Walk every module once. Offenders, population, stubs and unresolved bases.

    Cached because six assertions in this file need the same walk over ~2,000
    modules, and repeating it made this the slowest test in the repository.
    """
    offenders: dict[str, list[str]] = {}
    population: dict[str, int] = {}
    stubs: list[str] = []
    unresolved: list[str] = []
    function_prefixes, _ = _prefixes()

    for module in _test_modules():
        relative = module.relative_to(_REPO_ROOT)
        tree_name = relative.parts[0]
        parsed = _parse_module(module)
        source = module.read_text(encoding="utf-8")

        population[tree_name] = population.get(tree_name, 0) + _scanned_test_functions(parsed)
        for class_name, method, line in uncollected_test_methods(source, module):
            offenders.setdefault(tree_name, []).append(f"{relative}:{line} {class_name}.{method}")
        unresolved.extend(_unresolved_base_sites(parsed, relative, module))
        for node in parsed.body:
            if isinstance(node, ast.ClassDef) and _is_interface_stub(node):
                stubs.extend(
                    f"{relative}::{node.name}.{child.name}"
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and child.name.startswith(function_prefixes)
                )
    return (
        {tree: tuple(sites) for tree, sites in offenders.items()},
        population,
        tuple(stubs),
        tuple(unresolved),
    )


def _offenders_by_tree() -> dict[str, tuple[str, ...]]:
    return _scan()[0]


def _population_by_tree() -> dict[str, int]:
    return _scan()[1]


def test_the_population_is_present_and_large_enough_to_mean_anything() -> None:
    """Floors on the subject, not on the findings. Zero of zero is not clean."""
    modules = _test_modules()
    assert len(modules) >= _MIN_MODULES, (
        f"only {len(modules)} modules match pytest's python_files "
        f"{_pytest_option('python_files')} — expected at least {_MIN_MODULES}. "
        "The sweep has stopped matching and would call every tree clean."
    )
    total = sum(_population_by_tree().values())
    assert total >= _MIN_TEST_FUNCTIONS, (
        f"only {total} collectable test functions found across {len(modules)} modules "
        f"— expected at least {_MIN_TEST_FUNCTIONS}; the collector model has drifted "
        "from pytest's and this guard is looking at the wrong population"
    )


def test_no_tree_outside_the_known_set_holds_an_uncollected_test_method() -> None:
    """The hard zero, derived — no list to go stale."""
    offenders = _offenders_by_tree()
    surprises = {
        tree: sites for tree, sites in offenders.items() if tree not in _KNOWN_OFFENDERS
    }
    detail = "\n".join(
        f"  {tree}:\n    " + "\n    ".join(sorted(sites))
        for tree, sites in sorted(surprises.items())
    )
    assert not surprises, (
        "these test_* methods sit in a class pytest will not collect, in a tree "
        f"that was clean:\n{detail}\n"
        "Nothing runs them and they contribute zero to the suite total. Give the "
        "class a Test* name AND no __init__ (use setup_method), or derive it from "
        "unittest.TestCase, or move the methods to module level. If the class is a "
        "helper, rename the methods out of the test_* namespace (#14927)."
    )


def test_the_known_offender_budgets_only_ever_shrink() -> None:
    """Ratchet, both directions — a recorded shrink must be locked in (#14498).

    There is no sanctioned route to raise a number, and that is deliberate. A
    ``test_*`` method that nothing collects is never the right thing to write:
    every reader is told a check exists where none runs. Lowering a number needs
    no permission at all — fix a class and the assertion below names the new
    figure.
    """
    offenders = _offenders_by_tree()
    populations = _population_by_tree()

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
        "these trees gained a test_* method in a class pytest cannot collect "
        f"(actual, budget): {over}. The budgets are ceilings and there is no "
        "route to raise one (#14927)."
    )
    drained = sorted(tree for tree in _KNOWN_OFFENDERS if not offenders.get(tree))
    assert not drained, (
        f"{drained} no longer hold any uncollected test method — delete the entry "
        "from _KNOWN_OFFENDERS so the tree is pinned at zero by derivation. A "
        "budget left behind after the work is done is spendable, and it will be spent."
    )
    spent = {
        tree: (len(offenders.get(tree, [])), budget)
        for tree, (budget, _) in _KNOWN_OFFENDERS.items()
        if len(offenders.get(tree, [])) < budget
    }
    assert not spent, (
        "these trees are now BELOW their recorded budget (actual, budget): "
        f"{spent}. Lower the number here in the same commit, or the methods a fix "
        "collected can be spent back inside a stale tolerance."
    )


def test_the_interface_stub_exemption_has_not_grown() -> None:
    """The one exemption, pinned at its exact size.

    ``_MinimalConnector`` and ``_DummyConnector`` implement
    ``AbstractConnector.test_connection``; the production interface dictates the
    name, so neither renaming the method nor collecting the class is available.
    Exempting them is right. Leaving the exemption open-ended is not — "starts
    with an underscore" is a convention, and a convention with no ceiling is a
    bypass. A third stand-in must be looked at rather than absorbed.
    """
    stubs = _scan()[2]
    assert len(stubs) == _INTERFACE_STUBS, (
        f"the interface-stub exemption now covers {len(stubs)} methods, not "
        f"{_INTERFACE_STUBS}: {sorted(stubs)}. Each one is a test_* method nothing "
        "collects, exempted only because a production interface dictates its name. "
        "Confirm that is still true of every entry before changing this number."
    )


def test_no_test_class_inherits_init_from_an_unresolvable_base() -> None:
    """The explicit decision #14984 asks for, made loud instead of silent.

    A base this model cannot locate -- third-party, dynamically built, supplied
    by a star-import -- has an unknown ``__init__``. Unknown is not clean:
    ``_init_state`` reads it as ``__init__``-present, so the class's methods
    already count as offenders above. That is the safe direction but a confusing
    message, so every such class is named here as well, with the base that could
    not be reached. Measured zero on this branch.
    """
    unresolved = _scan()[3]
    assert not unresolved, (
        f"{len(unresolved)} Test* class(es) inherit from a base this guard cannot "
        "resolve, so whether pytest collects them is unknown:\n  "
        + "\n  ".join(sorted(unresolved))
        + "\npytest asks cls.__init__ is not object.__init__, which walks the MRO, so "
        "a constructor anywhere up the chain means the class is never collected and "
        "its test_* methods never run. Resolve it: import the base by a path this "
        "repo can follow, or give the class a base whose module is in the repo. The "
        "counts above treat these as uncollected on purpose -- an unreadable base is "
        "not a base that has been cleared (#14984)."
    )


def test_an_init_inherited_from_another_module_is_actually_followed() -> None:
    """The cross-module walk must be live, not merely written down.

    Two real classes reach their base through an absolute import
    (``ConnectorAcceptanceTest``, one package over). If the resolver silently
    returned "unknown" for every import, the assertion above would still pass by
    treating them as uncollected -- so the positive direction is pinned here: the
    base is found, and found to declare no constructor.
    """
    subclasses = [
        module
        for module in _test_modules()
        if "ConnectorAcceptanceTest" in module.read_text(encoding="utf-8")
        and "class Test" in module.read_text(encoding="utf-8")
    ]
    assert subclasses, (
        "no module inherits from ConnectorAcceptanceTest any more — this test pins "
        "the cross-module base walk to a real subject and now has none. Point it at "
        "another Test* class with an imported base, or the walk is unchecked (#14984)."
    )
    for module in subclasses:
        classes = {n.name: n for n in _parsed(module).body if isinstance(n, ast.ClassDef)}
        for name, node in classes.items():
            if not name.startswith("Test"):
                continue
            assert _init_state(node, classes, module) is False, (
                f"{module.relative_to(_REPO_ROOT)}::{name} — the base walk did not reach "
                "ConnectorAcceptanceTest through its import and settle its __init__ state"
            )


def test_a_base_in_a_neighbouring_module_carries_its_init_across(tmp_path: Path) -> None:
    """A relative import is followed too, and an inherited __init__ still blocks.

    Written as real files because the resolution under test is path-based: the
    source-string entry point on its own cannot see another module, and would
    fall back to "unknown" for every one of these.
    """
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "driver.py").write_text(
        "class Driver:\n    def __init__(self):\n        self.session = 1\n", encoding="utf-8"
    )
    (package / "clean.py").write_text("class Clean:\n    pass\n", encoding="utf-8")

    blocked = package / "blocked_test.py"
    blocked.write_text(
        "from .driver import Driver\n\n\nclass TestThing(Driver):\n"
        "    def test_one(self):\n        assert True\n",
        encoding="utf-8",
    )
    assert uncollected_test_methods(blocked.read_text(encoding="utf-8"), blocked) == [
        ("TestThing", "test_one", 5)
    ], "an __init__ imported from a neighbouring module still blocks collection"

    fine = package / "fine_test.py"
    fine.write_text(
        "from .clean import Clean\n\n\nclass TestThing(Clean):\n"
        "    def test_one(self):\n        assert True\n",
        encoding="utf-8",
    )
    assert not uncollected_test_methods(fine.read_text(encoding="utf-8"), fine), (
        "a resolved base with no constructor must not be reported — over-reporting "
        "gets a guard switched off as surely as under-reporting hides work"
    )


def test_the_detector_follows_an_inherited_init_up_the_mro() -> None:
    """#14984, driven through the same entry point the rest of the model uses.

    pytest asks ``cls.__init__ is not object.__init__``, which walks the MRO, so
    an inherited constructor blocks collection exactly as an own one does. The
    failure direction the old own-body-only check had was under-reporting: a
    real uncollected test recorded as fine.
    """
    assert uncollected_test_methods(
        "class Driver:\n    def __init__(self):\n        self.session = 1\n\n\n"
        "class TestThing(Driver):\n    def test_one(self):\n        pass\n"
    ) == [("TestThing", "test_one", 7)], "an __init__ inherited from a plain base still blocks collection"

    assert uncollected_test_methods(
        "class Driver:\n    def __init__(self):\n        self.session = 1\n\n\n"
        "class Middle(Driver):\n    pass\n\n\n"
        "class TestThing(Middle):\n    def test_one(self):\n        pass\n"
    ) == [("TestThing", "test_one", 11)], "the walk must follow a chain of bases, not just the first link"

    assert not uncollected_test_methods(
        "class Driver:\n    pass\n\n\n"
        "class TestThing(Driver):\n    def test_one(self):\n        pass\n"
    ), "a plain base with no constructor blocks nothing"

    assert not uncollected_test_methods(
        "class TestThing(object):\n    def test_one(self):\n        pass\n"
    ), "object is what pytest compares against, so spelling it out blocks nothing"

    # An import this model cannot follow is never read as clean -- see _init_state.
    assert uncollected_test_methods(
        "class TestThing(SomethingImported):\n    def test_one(self):\n        pass\n"
    ) == [("TestThing", "test_one", 2)], "an unresolvable base must not be assumed __init__-free"


def test_the_detector_finds_a_planted_method_and_spares_the_legitimate_ones() -> None:
    """Self-test. Every branch is exercised, not merely written down."""
    assert uncollected_test_methods("class Helper:\n    def test_a(self):\n        pass\n") == [
        ("Helper", "test_a", 2)
    ]

    # Collected, each for a different reason.
    assert not uncollected_test_methods("class TestX:\n    def test_a(self):\n        pass\n")
    assert not uncollected_test_methods(
        "import unittest\n\n\nclass Anything(unittest.TestCase):\n"
        "    def test_a(self):\n        pass\n"
    ), "unittest.TestCase is collected whatever python_classes says"
    assert not uncollected_test_methods(
        "import unittest\n\n\nclass Base(unittest.TestCase):\n    pass\n\n\n"
        "class Deeper(Base):\n    def test_a(self):\n        pass\n"
    ), "a TestCase subclass reached through another class in the module"
    assert not uncollected_test_methods(
        "class Mixin:\n    def test_a(self):\n        pass\n\n\n"
        "class TestReal(Mixin):\n    pass\n"
    ), "a base contributes its methods through any collected subclass"
    assert not uncollected_test_methods(
        "class _Stub(AbstractConnector):\n    async def test_connection(self):\n        pass\n"
    ), "a private stand-in implementing an interface that dictates the name"

    # The direction #14927 missed entirely.
    assert uncollected_test_methods(
        "class TestX:\n    def __init__(self):\n        pass\n\n"
        "    def test_a(self):\n        pass\n"
    ) == [("TestX", "test_a", 5)], "a Test* class with __init__ is NOT collected by pytest"

    # A module-level function is pytest's business, not this guard's.
    assert not uncollected_test_methods("def test_a():\n    pass\n")
    # A private stand-in with no base class is just a class named with an underscore.
    assert uncollected_test_methods("class _Loose:\n    def test_a(self):\n        pass\n")


_EVERY_SHAPE = '''
import unittest


class TestPlain:
    def test_collected_plain(self):
        assert True


class TestWithInit:
    def __init__(self):
        self.x = 1

    def test_blocked_by_init(self):
        assert True


class NotNamedTest:
    def test_blocked_by_name(self):
        assert True


class LowerCaseCase(unittest.TestCase):
    def test_collected_unittest(self):
        assert True


class Mixin:
    def test_collected_through_subclass(self):
        assert True


class TestFromMixin(Mixin):
    pass


class PlainBaseWithInit:
    def __init__(self):
        self.x = 1


class TestInheritsInit(PlainBaseWithInit):
    def test_blocked_by_inherited_init(self):
        assert True


class MiddleLink(PlainBaseWithInit):
    pass


class TestInheritsInitTwoLinksUp(MiddleLink):
    def test_blocked_two_links_up(self):
        assert True
'''


def test_the_model_agrees_with_pytest_on_every_shape(tmp_path: Path) -> None:
    """Run the real collector and compare. A model nothing checks is a guess.

    #14927 reported 120 methods from an AST model of ``python_classes`` alone.
    Collecting the files put the real figure at 90, with 30 false positives and
    41 real offenders the model could not see. That error is only catchable by
    asking pytest, so this asks pytest — on a module carrying one of every shape,
    in its own directory with its own config, so neither the repo's conftest nor
    its testpaths can influence the answer.
    """
    module = tmp_path / "shapes_test.py"
    module.write_text(textwrap.dedent(_EVERY_SHAPE), encoding="utf-8")
    config = tmp_path / "pytest.ini"
    config.write_text(
        "[pytest]\npython_files = test_*.py *_test.py\n"
        "python_classes = Test*\npython_functions = test_*\n",
        encoding="utf-8",
    )

    result = subprocess.run(  # nosec B603
        [
            sys.executable, "-m", "pytest", str(module),
            "--collect-only", "-q", "--no-header",
            "-c", str(config), "-p", "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    # Presence, not absence of failure: an empty stdout would otherwise agree
    # with a model that found nothing either.
    node_ids = {
        line.split("::")[-1].strip()
        for line in result.stdout.splitlines()
        if "::" in line and line.startswith("shapes_test.py")
    }
    assert node_ids, (
        "pytest collected nothing from the shape module, so this comparison proves "
        f"nothing.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    source = module.read_text(encoding="utf-8")
    every_method = {
        child.name
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        and child.name.startswith("test_")
    }
    predicted_uncollected = {method for _, method, _ in uncollected_test_methods(source)}
    predicted_collected = every_method - predicted_uncollected

    assert predicted_collected == node_ids, (
        "this file's model of pytest's collection disagrees with pytest.\n"
        f"  pytest collected : {sorted(node_ids)}\n"
        f"  model predicted  : {sorted(predicted_collected)}\n"
        "The model is what every count in this file rests on — fix it here, do not "
        "adjust the budgets to match a wrong model (#14927)."
    )


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
