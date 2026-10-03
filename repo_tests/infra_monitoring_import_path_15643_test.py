# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ``sys.path`` root a monitoring script inserts must hold the packages it imports.

``start_monitoring.py`` computed ``Path(__file__).parent.parent.parent`` and landed on
``autobot-infrastructure/shared/``, which has neither a ``constants`` nor a ``utils`` package, so
every one of its imports raised at module import time and the script could not start (#15643). Its
sibling ``start_hardware_monitoring.py`` had the same bug fixed in #14129 and the twin was never
carried along.

**Why this asserts the resolved DIRECTORY and not the expression.** The defect is a
correct-LOOKING expression landing in the wrong place: ``parent.parent.parent`` is valid Python,
reads plausibly, and is wrong by one level. A test pinning the literal expression would have
passed on the broken form and would fail on any future refactor that is equally correct, so it
licenses nothing. This resolves the expression and asserts the directory it names actually
contains the packages -- the property the script needs, rather than the spelling it used.

**Why it does not import the modules.** #15643's criterion asks for a test that imports the
surviving module. Executing these module bodies runs application code -- GPU capability probes and
a performance monitor -- which is both unavailable on a CI runner and out of bounds for a static
guard. A sibling test, ``start_monitoring_category_default_test.py``, does use ``exec_module`` and
would catch this defect, but it lives under ``autobot-infrastructure/`` which is absent from
``pytest.ini`` testpaths, so it has never run; its own docstring records that. This file lives in
``repo_tests/``, which IS in testpaths, so it runs today without touching that configuration.

The module list is DISCOVERED, not enumerated: a third monitoring script with the same bug is
covered the day it is added, where a hardcoded pair would have to be remembered.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

MONITORING_DIR = repo_root() / "autobot-infrastructure" / "shared" / "scripts" / "monitoring"

#: Floors. A discovery-based guard that finds nothing reports a clean run having asserted
#: nothing, which is the failure mode #15826 catalogues across this repo's tree scanners.
MIN_SCRIPTS = 2
MIN_REQUIREMENTS_CHECKED = 3


def _resolve_path_expr(node: ast.AST, script: Path) -> Path:
    """Evaluate the small path grammar these scripts use, or fail loudly.

    Deliberately NOT a general evaluator. An unsupported form raises, because silently skipping
    an expression this guard cannot read would turn an unparsed root into a pass -- the guard
    would then be measuring "roots I happened to understand", not "roots the script inserts".
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = node.right
        if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
            raise AssertionError(f"{script.name}: joined a non-literal onto a sys.path root")
        return _resolve_path_expr(node.left, script) / right.value
    if isinstance(node, ast.Subscript):  # .parents[N]
        value, index = node.value, node.slice
        if not (isinstance(value, ast.Attribute) and value.attr == "parents"):
            raise AssertionError(f"{script.name}: unsupported subscript in a sys.path root")
        if not (isinstance(index, ast.Constant) and isinstance(index.value, int)):
            raise AssertionError(f"{script.name}: non-literal parents[] index")
        return _resolve_path_expr(value.value, script).parents[index.value]
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        return _resolve_path_expr(node.value, script).parent
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "resolve":
            return _resolve_path_expr(func.value, script)
        if isinstance(func, ast.Name) and func.id == "Path":
            if len(node.args) == 1 and isinstance(node.args[0], ast.Name) and node.args[0].id == "__file__":
                return script.resolve()
            raise AssertionError(f"{script.name}: Path() built from something other than __file__")
    raise AssertionError(f"{script.name}: cannot statically resolve a sys.path root ({ast.dump(node)[:80]})")


def _assignments(tree: ast.Module) -> dict[str, ast.AST]:
    return {t.id: n.value for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}


def _inserted_roots(tree: ast.Module, script: Path) -> list[Path]:
    """Paths handed to ``sys.path.insert`` / ``sys.path.append``, resolved."""
    roots: list[Path] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"insert", "append"}:
            continue
        target = node.func.value
        if not (isinstance(target, ast.Attribute) and target.attr == "path"):
            continue
        for arg in node.args:
            expr = arg
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "str":
                expr = arg.args[0]
            if isinstance(expr, ast.Constant):
                continue
            if isinstance(expr, ast.Name):
                assigned = _assignments(tree).get(expr.id)
                if assigned is None:
                    raise AssertionError(f"{script.name}: sys.path root {expr.id} has no module-level assignment")
                expr = assigned
            roots.append(_resolve_path_expr(expr, script))
    return roots


def _is_external(name: str) -> bool:
    """Stdlib, or installed in site-packages -- never resolved against the repo."""
    if name in sys.stdlib_module_names:
        return True
    site = [p for p in sys.path if "site-packages" in p or "dist-packages" in p]
    if not site:
        return False
    from importlib.machinery import PathFinder

    return PathFinder().find_spec(name, site) is not None


def _local_import_roots(tree: ast.Module) -> set[str]:
    """First component of each ``from A.B import ...`` that is not stdlib or installed."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            head = node.module.split(".")[0]
            if not _is_external(head):
                names.add(head)
    return names


def _scripts() -> list[Path]:
    return sorted(p for p in MONITORING_DIR.glob("*.py") if not p.name.endswith("_test.py"))


def test_the_monitoring_directory_is_where_this_guard_thinks_it_is() -> None:
    """Reach floor: a moved or renamed directory must fail, never silently cover nothing."""
    assert MONITORING_DIR.is_dir(), f"{MONITORING_DIR} is missing; this guard would assert nothing"
    found = _scripts()
    assert len(found) >= MIN_SCRIPTS, f"expected at least {MIN_SCRIPTS} monitoring scripts, found {len(found)}"


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: p.name)
def test_every_inserted_sys_path_root_holds_the_packages_that_script_imports(script: Path) -> None:
    tree = ast.parse(script.read_text(encoding="utf-8"))
    roots = _inserted_roots(tree, script)
    needed = _local_import_roots(tree)
    if not needed:
        pytest.skip(f"{script.name} imports nothing that needs a sys.path root")
    # The repo root counts as a candidate alongside anything the script inserts: this is a
    # monorepo and its top-level packages (`autobot_shared`, ...) resolve without a sys.path
    # edit. Demanding an INSERTED root for those flagged both scripts on the first run of this
    # guard, which was the guard being wrong rather than the code -- `autobot_shared/` sits at
    # the repo root. `constants/` and `utils/` do NOT, so they still require an inserted root,
    # which is exactly the defect #15643 is about and the discrimination this test needs.
    candidates = [*roots, repo_root()]
    for package in sorted(needed):
        assert any((root / package).is_dir() for root in candidates), (
            f"{script.name} imports `{package}.*`, but neither the repo root nor any inserted "
            f"sys.path root contains a `{package}/` package. "
            f"Inserted roots resolved: {[str(r) for r in roots]}"
        )


def test_this_guard_actually_checked_some_requirements() -> None:
    """Second floor, over the ASSERTIONS rather than the files.

    Every script could be discovered, parsed and found to import nothing local -- and the
    parametrized test above would report all-green having compared no package against any root.
    A floor on files examined does not catch that; this one does.
    """
    checked = sum(len(_local_import_roots(ast.parse(s.read_text(encoding="utf-8")))) for s in _scripts())
    assert checked >= MIN_REQUIREMENTS_CHECKED, (
        f"only {checked} local import roots were checked across {len(_scripts())} scripts; "
        "expected at least "
        f"{MIN_REQUIREMENTS_CHECKED} -- a guard asserting almost nothing reports clean"
    )
