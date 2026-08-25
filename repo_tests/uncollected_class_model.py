# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""pytest's own collection rules, modelled over an AST (#14927, #14984).

A ``test_*`` method in a class pytest will not collect never runs. That is a
strictly worse defect than the one #14920 drains: a test that returns instead of
asserting is at least *counted* -- it appears in the total, it has a node id, and
a reader who looks for it finds it. A method in an uncollected class contributes
nothing at all. The file is named ``*_test.py``, it sits in a collected tree, it
imports cleanly, and every signal a reader has says the tests ran.
``security_idor_hotfix_test.py`` was believed for weeks to be in this state.

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

So this model is checked against pytest itself, in
``uncollected_class_model_test.py``, by running a real ``--collect-only`` over a
module carrying one of every shape. A model of a collector is worthless if
nothing ever compares it to the collector.

ONE GUARDED PARSE, ONCE PER MODULE
----------------------------------
``_parse_source`` is the only place text becomes a tree, and every entry point
goes through it, so a file the sweep cannot read fails by name instead of
raising ``SyntaxError`` somewhere a caller might absorb. ``_scan`` takes its tree
from ``_parsed``, the same cache base resolution reads, so each swept module is
read and parsed exactly once per run rather than twice (#15007).

This module holds no budgets and asserts nothing about the repository. The
numbers and the ratchet live in ``test_methods_in_uncollected_classes_test.py``;
the model's own self-tests live in ``uncollected_class_model_test.py``.
"""

from __future__ import annotations

import ast
import configparser
import functools
from pathlib import Path

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


def _pytest_option(name: str) -> list[str]:
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read(_PYTEST_INI, encoding="utf-8")
    values = parser.get("pytest", name, fallback="").split()
    assert values, f"pytest.ini declares no {name} — the population cannot be derived"
    return values


def _parse_source(source: str, path: Path | None) -> ast.Module:
    """The one place this guard turns text into a tree, so the guard is total.

    This sweep is a denylist walk from the repo root, filtered only by ``_SKIP``,
    so it reaches files pytest's ``testpaths`` allowlist never would: scratch
    copies, templates, half-written drafts. An unparseable one must never read as
    "clean" -- skipping it silently is the exact under-reporting failure this
    guard exists to catch -- so it is raised as a failure that names the file and
    says how to take it out of the sweep on purpose.

    Every entry point routes through here, the source-string one
    ``uncollected_test_methods`` exposes included. A second, bare ``ast.parse``
    anywhere would be a call path on which an unreadable subject raises
    ``SyntaxError`` instead of this, and a caller that caught it would be back to
    a file the sweep could not read reported as a file the sweep cleared
    (#15007).
    """
    try:
        return ast.parse(source)
    except SyntaxError as exc:
        named = (
            "<source>" if path is None
            else path.relative_to(_REPO_ROOT) if path.is_relative_to(_REPO_ROOT)
            else path
        )
        raise AssertionError(
            f"{named}:{exc.lineno or 0} is not parseable Python ({exc.msg}). "
            "This guard sweeps every *.py under the repo root as a denylist, so it "
            "sees files pytest's own testpaths allowlist never reaches. Fix the "
            "file, or -- if it is scratch, vendored or another branch's work and "
            "does not belong in the sweep -- add its top-level directory to _SKIP "
            "in every repo_tests guard that sweeps, the way .claude and .worktrees "
            "already are. Do not silence this by skipping the file: a file the "
            "sweep cannot read is not a file the sweep has cleared."
        ) from exc


def _parse_module(path: Path) -> ast.Module:
    """One swept file, read and parsed through the single guarded entry point."""
    return _parse_source(path.read_text(encoding="utf-8"), path)


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


def _imported_from(tree: ast.Module, dotted: str, origin: Path) -> tuple[Path, str] | None:
    """The file the head of ``dotted`` came from, and its real name in that file.

    The two are not the same name whenever the import is aliased. ``from mod
    import Foo as Bar`` binds ``Bar`` here, but ``mod`` keys its classes by
    ``Foo``, so resolving ``class TestThing(Bar)`` by the name it is *written*
    with looks up ``Bar`` in a dict that has never heard of it and reports the
    base as unreachable. That direction is safe -- unknown counts as
    ``__init__``-present, so the methods are still reported rather than spared --
    but it is a false "unresolvable base", and someone will go hunting a problem
    that is not there (#15007). Return the aliased-away name so the lookup uses
    it.

    ``import a.b.c`` needs no such rewrite: the head is bound to the package and
    the dotted base already spells out the real path to the class.
    """
    head, _, tail = dotted.partition(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if (alias.asname or alias.name) != head:
                    continue
                source = _module_path(node.module or "", node.level, origin)
                real = alias.name if alias.asname else head
                return None if source is None else (source, f"{real}.{tail}" if tail else real)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if (alias.asname or alias.name.split(".")[0]) == head:
                    source = _module_path(alias.name, 0, origin)
                    return None if source is None else (source, dotted)
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
    resolved = _imported_from(_parsed(module), dotted, module)
    if resolved is None:
        return None
    source, real = resolved
    outer = _module_classes(source)
    leaf = real.rsplit(".", 1)[-1]
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

    The sweep does not come through here: it has already parsed the file and
    calls ``_uncollected_from_tree`` with that tree, so no module is parsed twice
    in a run (#15007). This entry point exists for source that has no file.
    """
    return _uncollected_from_tree(_parse_source(source, module), module)


def _uncollected_from_tree(
    tree: ast.Module, module: Path | None = None
) -> list[tuple[str, str, int]]:
    """``uncollected_test_methods`` over an already-parsed tree."""
    function_prefixes, _ = _prefixes()
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
        # _parsed, not _parse_module: base resolution reaches back into this same
        # module through the cache, so the file is read and parsed exactly once.
        parsed = _parsed(module)

        population[tree_name] = population.get(tree_name, 0) + _scanned_test_functions(parsed)
        for class_name, method, line in _uncollected_from_tree(parsed, module):
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

