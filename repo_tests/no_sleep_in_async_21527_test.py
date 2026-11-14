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
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _discover(root: Path) -> list[str]:
    """Every tracked Python file; an empty tree yields [] so the floor raises the typed refusal."""
    try:
        return [rel for rel in tracked_paths(Path(root), ".") if rel.endswith(".py")]
    except EmptyEnumeration:
        return []


#: Measured on this tree: 8580 tracked .py files, so mid-window is 8580 - 400 / 2 = 8380 (skips=0).
REACH = declare(
    "no-sleep-in-async-21527",
    discover=_discover,
    floor=8380,  # measured on this tree; a new guard pins until it lands on the base (#19676)
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
        inner = isinstance(child, ast.AsyncFunctionDef) if isinstance(child, _FUNCTIONS) else in_async
        if isinstance(child, ast.Call) and in_async and _is_sleep(child, *names):
            hits.append(child.lineno)
        _walk(child, inner, names, hits)


def sleeps_in_async(source: str, filename: str = "<unknown>") -> list[int]:
    """Line numbers of every blocking `time.sleep` call made directly in an `async def`."""
    tree = parse_cache.parse(source, filename)
    hits: list[int] = []
    _walk(tree, False, _sleep_names(tree), hits)
    return hits


def _violations(root: Path) -> list[str]:
    found: list[str] = []
    for rel in REACH.examined(root):
        try:
            text = (root / rel).read_text(encoding="utf-8")
            lines = sleeps_in_async(text, rel)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        found.extend(f"{rel}:{line}" for line in lines)
    return found


def test_the_sweep_read_a_real_tree():
    files = REACH.examined(repo_root())
    REACH.completed(files, repo_root())


def test_no_tracked_python_sleeps_directly_inside_an_async_function():
    assert _violations(repo_root()) == []


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
