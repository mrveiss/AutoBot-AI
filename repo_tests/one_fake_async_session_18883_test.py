# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No new hand-rolled fake ``AsyncSession`` in a test; the one fake lives in testkit (#18883).

`autobot-backend/testkit/fake_async_session.py` is the one fake. Hand-rolled `_Session` classes
drifted from the real `AsyncSession` signature (a missing `attribute_names`, a keyword-only
`refresh`, a positional `with_for_update` on `get`), so a test passed on calls production
cannot make.

WHAT MATCHES (syntax tree only, so a comment or string naming these is not a site)
    A class whose OWN body defines any of `commit`, `refresh`, `flush`, `execute`, `add` -- as an
    `async def`, a plain `def`, a class-level assignment (`commit = AsyncMock()`, annotated or not)
    or an instance assignment in one of its methods (`self.commit = AsyncMock()`) -- and which does
    not extend the canonical `FakeAsyncSession` (resolved through the import of
    `testkit.fake_async_session`, so a same-named local base does not exempt it). Also the
    three-argument `type("Name", bases, {"commit": ...})` form whose dict literal has such a key
    (a factory function returning one is judged the same way: the call is the site). A nested class
    is judged on its own body. Each is keyed `path::enclosing_function::ClassName`
    (`<module>` when defined at module level); the 2nd, 3rd... same-named class in one function gets
    `#2`, `#3`, so they cannot collapse into one entry.
BOUNDARY
    Scanned: tracked `.py` in `SCAN_ROOTS` that is a test file (`*_test.py`, `test_*.py`,
    `conftest.py`) OR sits under a directory named `tests` or `testkit` at any depth. That second
    arm is what brings in non-test helper modules (`tests/**/fakes.py`, `tests/**/_*.py`,
    `testkit/*.py`). Exempt by path: the canonical fake, and the canonical Redis pipeline fake
    (`testkit/fake_redis_pipeline.py`, #18991 -- a pipeline's `execute` is not a session's).
    NOT seen: a `MagicMock`/`AsyncMock` built inline with no class, a test double outside
    `SCAN_ROOTS`, and a helper module outside a `tests`/`testkit` directory that is not named like
    a test. Those are separate findings.

THE ALLOWLIST (`hand_rolled_async_session_baseline_18883.py`) freezes today's offenders. It may
only shrink: a new match fails, a stale entry fails. Migrating a file deletes its lines.
"""

from __future__ import annotations

import ast
import functools
from collections import Counter
from pathlib import Path
from typing import Optional

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.hand_rolled_async_session_baseline_18883 import ALLOWLIST, FROZEN_TOTAL

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

CANONICAL = "autobot-backend/testkit/fake_async_session.py"
#: Also exempt by path: the canonical Redis pipeline fake (#18991), whose `execute` is the pipeline's, not a session's.
CANONICAL_PIPELINE = "autobot-backend/testkit/fake_redis_pipeline.py"
CANONICAL_NAME = "FakeAsyncSession"
CANONICAL_MODULE = "testkit.fake_async_session"
SCAN_ROOTS = ("autobot-backend", "autobot-slm-backend")
_SESSION_METHODS = frozenset({"commit", "refresh", "flush", "execute", "add"})
HELPER_DIRS = frozenset({"tests", "testkit"})


def _is_test_file(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py"


def _is_scanned(rel: str) -> bool:
    if not rel.endswith(".py") or rel in (CANONICAL, CANONICAL_PIPELINE):
        return False
    return _is_test_file(rel) or bool(HELPER_DIRS & set(rel.split("/")[:-1]))


def _assigned_names(node: ast.AST, *, self_only: bool = False) -> set[str]:
    """Names a statement assigns: plain names (class level only) and `self.` attributes."""
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return set()
    names: set[str] = set()
    for target in targets:
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
            names.add(target.attr)
        elif isinstance(target, ast.Name) and not self_only:
            names.add(target.id)
    return names


def _defines_session_method(cls: ast.ClassDef) -> bool:
    """Own body only: a method, a class-level assignment, or a `self.X =` in one of its methods."""
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            inner = {n for sub in ast.walk(node) for n in _assigned_names(sub, self_only=True)}
            if node.name in _SESSION_METHODS or inner & _SESSION_METHODS:
                return True
        elif _assigned_names(node) & _SESSION_METHODS:
            return True
    return False


def _canonical_bindings(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Names bound to the canonical class, and names bound to the canonical module, by import."""
    module_stem = CANONICAL_MODULE.rsplit(".", 1)[-1]
    classes: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == CANONICAL_MODULE:
            classes.update(a.asname or a.name for a in node.names if a.name == CANONICAL_NAME)
        elif isinstance(node, ast.ImportFrom) and node.module == CANONICAL_MODULE.rsplit(".", 1)[0]:
            modules.update(a.asname or a.name for a in node.names if a.name == module_stem)
        elif isinstance(node, ast.Import):
            modules.update(a.asname or a.name for a in node.names if a.name == CANONICAL_MODULE)
    return classes, modules


def _is_canonical_base(base: ast.AST, classes: set[str], modules: set[str]) -> bool:
    if isinstance(base, ast.Name):
        return base.id in classes
    return isinstance(base, ast.Attribute) and base.attr == CANONICAL_NAME and ast.unparse(base.value) in modules


def _extends_canonical(cls: ast.ClassDef, classes: set[str], modules: set[str]) -> bool:
    """True when a base IS the canonical class by import, not merely one with the same name."""
    return any(_is_canonical_base(base, classes, modules) for base in cls.bases)


def _type_call_name(node: ast.AST, bound: tuple[set[str], set[str]]) -> Optional[str]:
    """`Name` of `type("Name", bases, {"commit": ...})` when the dict defines a session method, else None."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "type"):
        return None
    if len(node.args) != 3 or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[2], ast.Dict):
        return None
    keys = {k.value for k in node.args[2].keys if isinstance(k, ast.Constant)}
    bases = node.args[1].elts if isinstance(node.args[1], ast.Tuple) else []
    if not keys & _SESSION_METHODS or any(_is_canonical_base(b, *bound) for b in bases):
        return None
    return str(node.args[0].value)


def _site(child: ast.AST, bound: tuple[set[str], set[str]]) -> Optional[str]:
    if isinstance(child, ast.ClassDef):
        if _defines_session_method(child) and not _extends_canonical(child, *bound):
            return child.name
        return None
    return _type_call_name(child, bound)


def _visit(node: ast.AST, enclosing: str, found: list[tuple[str, str]], bound: tuple[set[str], set[str]]) -> None:
    for child in ast.iter_child_nodes(node):
        name = _site(child, bound)
        if name is not None:
            found.append((enclosing, name))
        scope = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else enclosing
        _visit(child, scope, found, bound)


def hand_rolled_sessions(source: str) -> list[tuple[str, str]]:
    """`(enclosing function, class name)` for every hand-rolled session class in `source`."""
    found: list[tuple[str, str]] = []
    tree = ast.parse(source)
    _visit(tree, "<module>", found, _canonical_bindings(tree))
    return found


def finding_keys(rel: str, source: str) -> list[str]:
    """`path::func::Class`, with `#2`, `#3` for the 2nd, 3rd... same-named class in one function."""
    seen: Counter = Counter()
    keys: list[str] = []
    for func, name in hand_rolled_sessions(source):
        seen[(func, name)] += 1
        n = seen[(func, name)]
        keys.append(f"{rel}::{func}::{name}" + (f"#{n}" if n > 1 else ""))
    return keys


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *SCAN_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_scanned(rel)]


REACH = declare(
    "hand-rolled-async-session-scan",
    discover=_population,
    # Mid-window, from REACH.window(): population 2431 (test files + tests/testkit helpers) -> (2231, 2431, 2331).
    floor=2412,  # re-pinned mid-window (train 81 on main)
    what="test python source",
    roots=SCAN_ROOTS,
    growth=200,
)


@functools.lru_cache(maxsize=1)
def _found() -> frozenset[str]:
    keys: set[str] = set()
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        keys.update(finding_keys(rel, source))
    return frozenset(keys)


_HAND_ROLLED = """
def make():
    class _Session:
        async def commit(self):
            pass
        async def refresh(self, obj):
            pass
    return _Session()
"""
_TWO_IN_ONE_FILE = """
def a():
    class _Session:
        async def commit(self): ...
def b():
    class _Session:
        async def refresh(self, o): ...
"""
_MODULE_LEVEL = "class Fake:\n    async def commit(self):\n        pass\n"
_SUBCLASS = "from testkit.fake_async_session import FakeAsyncSession\nclass S(FakeAsyncSession):\n    async def commit(self):\n        pass\n"
_LOCAL_SAME_NAME = (
    "class FakeAsyncSession:\n    pass\nclass S(FakeAsyncSession):\n    async def commit(self):\n        pass\n"
)
_ALIASED = "from testkit.fake_async_session import FakeAsyncSession as F\nclass S(F):\n    async def commit(self):\n        pass\n"
_QUALIFIED = "import testkit.fake_async_session as t\nclass S(t.FakeAsyncSession):\n    async def refresh(self, o):\n        pass\n"
_CANONICAL_IMPORT = "from testkit.fake_async_session import FakeAsyncSession\n"
_TYPE_FAKE = "def make():\n    return type('_S', (), {'commit': None})\n"
_TYPE_FACTORY = "def build():\n    cls = type('_S', (), {'execute': lambda self: None})\n    return cls\n"
_TYPE_CANONICAL = _CANONICAL_IMPORT + "X = type('S', (FakeAsyncSession,), {'commit': None})\n"
_FACTORY_CLASS = "def factory():\n    class _S:\n        def add(self, o): ...\n    return _S\n"


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a class inside a function", _HAND_ROLLED, [("make", "_Session")]),
        ("same name, two functions", _TWO_IN_ONE_FILE, [("a", "_Session"), ("b", "_Session")]),
        ("module level", _MODULE_LEVEL, [("<module>", "Fake")]),
        ("a subclass of the canonical fake", _SUBCLASS, []),
        ("a qualified canonical base", _QUALIFIED, []),
        ("an aliased canonical import", _ALIASED, []),
        ("a same-named local base is not the canonical one", _LOCAL_SAME_NAME, [("<module>", "S")]),
        ("a sync commit is a session", "class C:\n    def commit(self):\n        pass\n", [("<module>", "C")]),
        ("a sync add", "class C:\n    def add(self, o):\n        pass\n", [("<module>", "C")]),
        ("an async execute", "class C:\n    async def execute(self):\n        pass\n", [("<module>", "C")]),
        ("a flush", "class C:\n    async def flush(self):\n        pass\n", [("<module>", "C")]),
        ("an unrelated method", "class C:\n    async def fetch(self):\n        pass\n", []),
        ("a class-level AsyncMock assignment", "class C:\n    commit = AsyncMock()\n", [("<module>", "C")]),
        ("an annotated class-level assignment", "class C:\n    refresh: object = None\n", [("<module>", "C")]),
        (
            "an instance assignment in __init__",
            "class C:\n    def __init__(self):\n        self.execute = 1\n",
            [("<module>", "C")],
        ),
        (
            "a local variable named like a method is not a member",
            "class C:\n    def f(self):\n        commit = 1\n",
            [],
        ),
        ("type() with a session method", _TYPE_FAKE, [("make", "_S")]),
        ("type() bound to a name in a factory", _TYPE_FACTORY, [("build", "_S")]),
        ("type() without a session method", "X = type('M', (), {'id': 1})\n", []),
        ("type() extending the canonical fake", _TYPE_CANONICAL, []),
        ("a factory returning a class", _FACTORY_CLASS, [("factory", "_S")]),
        ("comments and strings only", '# async def commit\nclass C:\n    """async def refresh"""\n', []),
        (
            "a nested class is judged on its own body",
            "class Outer:\n    class Inner:\n        async def commit(self): ...\n",
            [("<module>", "Inner")],
        ),
    ],
)
def test_the_detector_tells_a_hand_rolled_session_from_a_lookalike(
    label: str, source: str, expected: list[tuple[str, str]]
) -> None:
    assert hand_rolled_sessions(source) == expected, label


def test_two_same_named_classes_in_one_function_get_distinct_keys() -> None:
    source = "def f():\n    class _S:\n        def add(self): ...\n    class _S:\n        def add(self): ...\n"
    assert finding_keys("p.py", source) == ["p.py::f::_S", "p.py::f::_S#2"]
    assert finding_keys("p.py", "class A:\n    def add(self): ...\nclass B:\n    def add(self): ...\n") == [
        "p.py::<module>::A",
        "p.py::<module>::B",
    ]


def test_the_canonical_module_is_exempt_and_tests_and_test_helpers_are_scanned() -> None:
    assert not _is_scanned(CANONICAL)
    assert not _is_scanned(CANONICAL_PIPELINE)
    assert _is_scanned("autobot-backend/foo/x_test.py")
    assert _is_scanned("autobot-backend/foo/test_x.py")
    assert _is_scanned("autobot-slm-backend/conftest.py")
    # non-test helper modules under a tests/ or testkit/ directory, at any depth
    assert _is_scanned("autobot-backend/foo/tests/helpers.py")
    assert _is_scanned("autobot-backend/tests/api/fakes.py")
    assert _is_scanned("autobot-backend/tests/api/_doubles.py")
    assert _is_scanned("autobot-backend/testkit/fake_result.py")
    # contrast: production code, and a non-python file under a test dir
    assert not _is_scanned("autobot-backend/foo/service.py")
    assert not _is_scanned("autobot-backend/testing_utils/fakes.py")
    assert not _is_scanned("autobot-backend/tests/data.json")


def test_the_scan_is_not_vacuous() -> None:
    """Bind the floor to the scan's reach, never to the finding count (it may reach zero)."""
    assert len(REACH.examined(repo_root())) > 2000


def test_no_new_hand_rolled_async_session() -> None:
    new = sorted(_found() - set(ALLOWLIST))
    assert not new, (
        f"#18883: {new} define a fake async session (commit/refresh) by hand. Use {CANONICAL} "
        f"({CANONICAL_NAME}, FakeResult); pass opt-ins through its constructor."
    )


def test_every_allowlist_entry_still_matches() -> None:
    stale = sorted(set(ALLOWLIST) - _found())
    assert not stale, f"stale allowlist entries (class gone or migrated); delete these lines: {stale}"


def test_the_allowlist_only_shrinks_and_every_entry_has_a_reason() -> None:
    assert len(ALLOWLIST) <= FROZEN_TOTAL, f"{len(ALLOWLIST)} entries exceeds the frozen {FROZEN_TOTAL}"
    assert all(reason.strip() for reason in ALLOWLIST.values())
