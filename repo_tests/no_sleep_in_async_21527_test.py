# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`time.sleep` is never called directly inside an `async def` (#21527).

A blocking sleep in a coroutine stalls every other task on the event loop. A census at the time of
filing found none in production code and six in two test files; those now control the clock instead
of waiting on it, and this keeps the count at zero.

What it sees: a call to `time.sleep`, to `sleep` imported with `from time import sleep`, and to either
under an alias (`import time as t`, `from time import sleep as nap`), whose INNERMOST enclosing
function is an `async def`. A sync `def` (or a lambda) nested inside an `async def` is not a hit; an
`async def` nested inside a sync one is.

What it does NOT see: a sync helper that sleeps and is called from async code, any other blocking call
(`requests`, `subprocess.run`, file I/O), and a `time` module reached any way other than a plain
import in the same file. Those are not claimed clean.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import ReachFloorError, declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _discover(root: Path) -> list[str]:
    """Every tracked Python file; an empty tree yields [] so the floor raises the typed refusal."""
    try:
        return [rel for rel in tracked_paths(Path(root), ".") if rel.endswith(".py")]
    except EmptyEnumeration:
        return []


#: Measured on this tree (guard's own file included): 8584 tracked .py files, so mid-window is 8584 - 400 / 2 = 8384 (skips=0).
REACH = declare(
    "no-sleep-in-async-21527",
    discover=_discover,
    floor=8384,  # measured on this tree; a new guard pins until it lands on the base (#19676)
    growth=400,
    what="tracked Python files swept for time.sleep inside async def",
)


def _sleep_names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """(local names bound to the `time` module, local names bound to `time.sleep`)."""
    modules: set[str] = set()
    functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update((a.asname or a.name) for a in node.names if a.name == "time")
        elif isinstance(node, ast.ImportFrom) and node.module == "time" and node.level == 0:
            functions.update((a.asname or a.name) for a in node.names if a.name == "sleep")
    return modules, functions


def _is_sleep(call: ast.Call, modules: set[str], functions: set[str]) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in functions
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "sleep"
        and isinstance(func.value, ast.Name)
        and func.value.id in modules
    )


def _walk(node: ast.AST, in_async: bool, names, hits: list[int]) -> None:
    """Visit `node`'s children; `in_async` is whether the innermost enclosing function is `async def`."""
    for child in ast.iter_child_nodes(node):
        _visit(child, in_async, names, hits)


def _visit(node: ast.AST, in_async: bool, names, hits: list[int]) -> None:
    if isinstance(node, ast.Call) and in_async and _is_sleep(node, *names):
        hits.append(node.lineno)
    if not isinstance(node, _FUNCTIONS):
        _walk(node, in_async, names, hits)
        return
    # Decorators, defaults and annotations run in the ENCLOSING scope when the def statement runs; only the
    # body switches context.
    body_context = isinstance(node, ast.AsyncFunctionDef)
    for field, value in ast.iter_fields(node):
        context = body_context if field == "body" else in_async
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, ast.AST):
                _visit(item, context, names, hits)


def sleeps_in_async(source: str, filename: str = "<unknown>") -> list[int]:
    """Line numbers of every blocking `time.sleep` call made directly in an `async def`."""
    tree = parse_cache.parse(source, filename)
    hits: list[int] = []
    _walk(tree, False, _sleep_names(tree), hits)
    return hits


def _sweep(root: Path, files) -> tuple[list[str], int]:
    """(`path:line` of every hit, files actually read AND parsed). An unreadable or unparsable file is
    skipped and not counted, so the completion floor sees the work done rather than the work available."""
    found: list[str] = []
    scanned = 0
    for rel in files:
        try:
            text = (root / rel).read_text(encoding="utf-8")
            lines = sleeps_in_async(text, rel)
        except (SyntaxError, UnicodeDecodeError, OSError, ValueError):
            continue
        scanned += 1
        found.extend(f"{rel}:{line}" for line in lines)
    return found, scanned


@functools.cache
def _live() -> tuple[list[str], int]:
    root = repo_root()
    return _sweep(root, REACH.examined(root))


def test_the_sweep_read_and_parsed_a_real_tree():
    REACH.completed(_live()[1], repo_root())


def test_no_tracked_python_sleeps_directly_inside_an_async_function():
    assert _live()[0] == []


def test_contrast_discovery_succeeding_while_every_parse_fails_is_refused(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    found, scanned = _sweep(tmp_path, ["bad.py"])
    assert (found, scanned) == ([], 0)
    with pytest.raises(ReachFloorError):
        REACH.completed(scanned, tmp_path)


_ASYNC = "async def f():\n    {call}\n"


def test_contrast_the_plain_spelling_is_found():
    assert sleeps_in_async("import time\n" + _ASYNC.format(call="time.sleep(1)")) == [3]


def test_contrast_a_from_import_is_found():
    assert sleeps_in_async("from time import sleep\n" + _ASYNC.format(call="sleep(1)")) == [3]


def test_contrast_an_aliased_module_is_found():
    assert sleeps_in_async("import time as t\n" + _ASYNC.format(call="t.sleep(1)")) == [3]


def test_contrast_an_aliased_function_is_found():
    assert sleeps_in_async("from time import sleep as nap\n" + _ASYNC.format(call="nap(1)")) == [3]


def test_contrast_a_sync_function_and_an_async_sleep_in_one_file():
    source = "import time\ndef a():\n    time.sleep(1)\nasync def b():\n    await asyncio.sleep(1)\n"
    assert sleeps_in_async(source) == []


def test_contrast_a_sync_def_nested_in_an_async_def_is_not_a_hit():
    source = "import time\nasync def f():\n    def inner():\n        time.sleep(1)\n    return inner\n"
    assert sleeps_in_async(source) == []


def test_contrast_an_async_def_nested_in_a_sync_def_is_a_hit():
    source = "import time\ndef f():\n    async def inner():\n        time.sleep(1)\n    return inner\n"
    assert sleeps_in_async(source) == [4]


def test_contrast_an_unrelated_sleep_is_not_a_hit():
    assert sleeps_in_async("async def f(clock):\n    clock.sleep(1)\n    sleep(1)\n") == []


def test_contrast_a_planted_violation_is_reported_with_its_path(tmp_path):
    target = tmp_path / "pkg" / "mod.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("import time\nasync def f():\n    time.sleep(1)\n", encoding="utf-8")
    assert sleeps_in_async(target.read_text(encoding="utf-8"), "pkg/mod.py") == [3]


def test_contrast_a_nested_sync_defs_default_runs_in_the_coroutine():
    source = "import time\nasync def f():\n    def inner(delay=time.sleep(1)):\n        return delay\n"
    assert sleeps_in_async(source) == [3]


def test_contrast_a_nested_sync_defs_keyword_only_default_and_lambda_default_are_hits():
    source = "import time\nasync def f():\n    def a(*, d=time.sleep(1)): ...\n    return lambda x=time.sleep(1): x\n"
    assert sleeps_in_async(source) == [3, 4]


def test_contrast_a_nested_sync_defs_decorator_runs_in_the_coroutine():
    source = "import time\nasync def f():\n    @time.sleep(1)\n    def inner():\n        pass\n"
    assert sleeps_in_async(source) == [3]


def test_contrast_a_nested_class_base_runs_in_the_coroutine():
    source = "import time\nasync def f():\n    class C(time.sleep(1)):\n        pass\n"
    assert sleeps_in_async(source) == [3]


def test_contrast_a_module_level_async_defs_own_default_is_evaluated_at_import():
    assert sleeps_in_async("import time\nasync def f(d=time.sleep(1)):\n    return d\n") == []
