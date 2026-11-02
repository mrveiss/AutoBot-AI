# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No new hand-rolled Redis pipeline double in a test; the one fake lives in testkit (#18991).

`autobot-backend/testkit/fake_redis_pipeline.py` (`FakePipeline`, `FakeAsyncPipeline`) is the one
fake. Eighteen hand-rolled `_FakePipeline` / `_Pipe` classes each re-decided whether commands apply
at call time or at `execute`, what `execute` returns, and whether `watch`/`multi`/`WatchError` exist
at all -- so a test could pass for code that forgot to call `execute`.

WHAT MATCHES (syntax tree only, so a comment or string naming these is not a site)
    A class whose name contains `pipe` (any case) and whose OWN body defines `execute` -- as a
    `def`, an `async def`, a class-level assignment (`execute = AsyncMock()`) or an instance
    assignment in one of its methods (`self.execute = AsyncMock()`) -- PLUS at least one queueing
    member: any other own member that is not a dunder and not pipeline lifecycle (`reset`, `watch`,
    `unwatch`, `multi`, `discard`, `json`). It does not extend the canonical `FakePipeline` /
    `FakeAsyncPipeline` (resolved through the import of `testkit.fake_redis_pipeline`, so a
    same-named local base does not exempt it). A nested class is judged on its own body. Each is
    keyed `path::enclosing_function::ClassName` (`<module>` at module level; `#2`, `#3` for the 2nd,
    3rd... same-named class in one function).
BOUNDARY
    Scanned: tracked `.py` under `SCAN_ROOTS` that is a test file (`*_test.py`, `test_*.py`,
    `conftest.py`) OR sits under a directory named `tests` or `testkit`, judged on the
    REPO-RELATIVE path (a checkout living under a directory named `tests` changes nothing, #18972).
    Exempt by path: the canonical module only.
    NOT seen: a pipeline double whose class name lacks `pipe`, a `MagicMock` pipeline built inline,
    and a double outside `SCAN_ROOTS`. Those are separate findings.

THE ALLOWLIST (`hand_rolled_redis_pipeline_baseline_18991.py`) is empty and may only shrink.
"""

from __future__ import annotations

import ast
import functools
from collections import Counter
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.hand_rolled_redis_pipeline_baseline_18991 import ALLOWLIST, FROZEN_TOTAL

from autobot_shared.isolated_git import git, make_repo
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

CANONICAL = "autobot-backend/testkit/fake_redis_pipeline.py"
CANONICAL_MODULE = "testkit.fake_redis_pipeline"
CANONICAL_NAMES = frozenset({"FakePipeline", "FakeAsyncPipeline"})
SCAN_ROOTS = ("autobot-backend", "autobot-slm-backend")
HELPER_DIRS = frozenset({"tests", "testkit"})
_LIFECYCLE = frozenset({"execute", "reset", "watch", "unwatch", "multi", "discard", "json"})


def _is_test_file(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py"


def _is_scanned(rel: str) -> bool:
    if not rel.endswith(".py") or rel == CANONICAL:
        return False
    return _is_test_file(rel) or bool(HELPER_DIRS & set(rel.split("/")[:-1]))


def _assigned(node: ast.AST, *, self_only: bool) -> set[str]:
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


def _own_members(cls: ast.ClassDef) -> set[str]:
    """Own body only: methods, class-level assignments, and `self.X =` inside its methods."""
    members: set[str] = set()
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            members.add(node.name)
            members.update(n for sub in ast.walk(node) for n in _assigned(sub, self_only=True))
        else:
            members.update(_assigned(node, self_only=False))
    return members


def _is_pipeline_double(cls: ast.ClassDef) -> bool:
    members = _own_members(cls)
    queueing = {m for m in members if not (m.startswith("__") and m.endswith("__"))} - _LIFECYCLE
    return "pipe" in cls.name.lower() and "execute" in members and bool(queueing)


def _canonical_bindings(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Names bound to the canonical classes, and names bound to the canonical module, by import."""
    parent, stem = CANONICAL_MODULE.rsplit(".", 1)
    classes: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == CANONICAL_MODULE:
            classes.update(a.asname or a.name for a in node.names if a.name in CANONICAL_NAMES)
        elif isinstance(node, ast.ImportFrom) and node.module == parent:
            modules.update(a.asname or a.name for a in node.names if a.name == stem)
        elif isinstance(node, ast.Import):
            modules.update(a.asname or a.name for a in node.names if a.name == CANONICAL_MODULE)
    return classes, modules


def _is_canonical_base(base: ast.AST, classes: set[str], modules: set[str]) -> bool:
    if isinstance(base, ast.Name):
        return base.id in classes
    return isinstance(base, ast.Attribute) and base.attr in CANONICAL_NAMES and ast.unparse(base.value) in modules


def _visit(node: ast.AST, enclosing: str, found: list[tuple[str, str]], bound: tuple[set[str], set[str]]) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef) and _is_pipeline_double(child):
            if not any(_is_canonical_base(base, *bound) for base in child.bases):
                found.append((enclosing, child.name))
        scope = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else enclosing
        _visit(child, scope, found, bound)


def hand_rolled_pipelines(source: str) -> list[tuple[str, str]]:
    """`(enclosing function, class name)` for every hand-rolled pipeline double in `source`."""
    found: list[tuple[str, str]] = []
    tree = ast.parse(source)
    _visit(tree, "<module>", found, _canonical_bindings(tree))
    return found


def finding_keys(rel: str, source: str) -> list[str]:
    """`path::func::Class`, with `#2`, `#3` for the 2nd, 3rd... same-named class in one function."""
    seen: Counter = Counter()
    keys: list[str] = []
    for func, name in hand_rolled_pipelines(source):
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


def _all_python(root: Path) -> int:
    """Every tracked `.py` under the roots, tests included -- the reference population."""
    try:
        return sum(1 for rel in tracked_paths(root, *SCAN_ROOTS) if rel.endswith(".py"))
    except EmptyEnumeration:
        return 0


REACH = declare(
    "hand-rolled-redis-pipeline-scan",
    discover=_population,
    reference=_all_python,
    min_fraction=0.40,
    what="test python source",
    roots=SCAN_ROOTS,
)


@functools.lru_cache(maxsize=1)
def _found() -> frozenset[str]:
    keys: set[str] = set()
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        keys.update(finding_keys(rel, source))
    return frozenset(keys)


_HAND_ROLLED = """
class _FakePipeline:
    def __init__(self):
        self.q = []
    def hget(self, key, field):
        self.q.append(key)
        return self
    async def execute(self):
        return []
"""
_ASYNC_MOCK_STYLE = """
class _FakePipe:
    def __init__(self):
        self.sadd = AsyncMock()
        self.execute = AsyncMock(return_value=[])
"""
_CLASS_LEVEL = "class _Pipe:\n    execute = AsyncMock()\n    sadd = AsyncMock()\n"
_IN_FUNCTION = "def make():\n    class _Pipe:\n        def set(self, k, v): ...\n        async def execute(self): ...\n    return _Pipe()\n"
_SUBCLASS = (
    "from testkit.fake_redis_pipeline import FakeAsyncPipeline\n"
    "class _Pipe(FakeAsyncPipeline):\n    def custom(self): ...\n    async def execute(self): ...\n"
)
_ALIASED = (
    "from testkit.fake_redis_pipeline import FakeAsyncPipeline as P\n"
    "class _Pipe(P):\n    def custom(self): ...\n    async def execute(self): ...\n"
)
_QUALIFIED = (
    "import testkit.fake_redis_pipeline as t\n"
    "class _Pipe(t.FakePipeline):\n    def custom(self): ...\n    def execute(self): ...\n"
)
_MODULE_IMPORT = (
    "from testkit import fake_redis_pipeline as f\n"
    "class _Pipe(f.FakePipeline):\n    def custom(self): ...\n    def execute(self): ...\n"
)
_LOCAL_SAME_NAME = (
    "class FakeAsyncPipeline:\n    pass\n"
    "class _Pipe(FakeAsyncPipeline):\n    def custom(self): ...\n    async def execute(self): ...\n"
)
_NO_QUEUEING = (
    "class _Pipe:\n    async def execute(self): ...\n    async def reset(self): ...\n    def __init__(self): ...\n"
)
_NO_EXECUTE = "class _Pipe:\n    def hget(self, k, f): ...\n"
_NOT_A_PIPE = "class _Queue:\n    def hget(self, k, f): ...\n    async def execute(self): ...\n"
_CANONICAL_IMPORT_ONLY = "from testkit.fake_redis_pipeline import FakeAsyncPipeline\nX = FakeAsyncPipeline()\n"


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a hand-rolled pipeline", _HAND_ROLLED, [("<module>", "_FakePipeline")]),
        ("AsyncMock attributes assigned in __init__", _ASYNC_MOCK_STYLE, [("<module>", "_FakePipe")]),
        ("class-level assignments", _CLASS_LEVEL, [("<module>", "_Pipe")]),
        ("a class inside a function", _IN_FUNCTION, [("make", "_Pipe")]),
        (
            "a case-insensitive name",
            "class DictPIPELINE:\n    def set(self): ...\n    def execute(self): ...\n",
            [("<module>", "DictPIPELINE")],
        ),
        ("a subclass of the canonical fake", _SUBCLASS, []),
        ("an aliased canonical base", _ALIASED, []),
        ("a qualified canonical base", _QUALIFIED, []),
        ("a from-package module import", _MODULE_IMPORT, []),
        ("a same-named local base is not the canonical one", _LOCAL_SAME_NAME, [("<module>", "_Pipe")]),
        ("execute with no queueing member", _NO_QUEUEING, []),
        ("queueing members with no execute", _NO_EXECUTE, []),
        ("a class not named like a pipeline", _NOT_A_PIPE, []),
        ("importing the canonical fake and using it", _CANONICAL_IMPORT_ONLY, []),
        ("comments and strings only", '# class _Pipe: def execute\n"""def hget"""\n', []),
        (
            "a nested class is judged on its own body",
            "class Outer:\n    class _Pipe:\n        def hget(self): ...\n        def execute(self): ...\n",
            [("<module>", "_Pipe")],
        ),
    ],
)
def test_the_detector_tells_a_hand_rolled_pipeline_from_a_lookalike(
    label: str, source: str, expected: list[tuple[str, str]]
) -> None:
    assert hand_rolled_pipelines(source) == expected, label


def test_two_same_named_classes_in_one_function_get_distinct_keys() -> None:
    body = "    class _Pipe:\n        def hget(self): ...\n        def execute(self): ...\n"
    assert finding_keys("p.py", "def f():\n" + body + body) == ["p.py::f::_Pipe", "p.py::f::_Pipe#2"]


def test_the_canonical_module_is_exempt_and_tests_and_test_helpers_are_scanned() -> None:
    assert not _is_scanned(CANONICAL)
    assert _is_scanned("autobot-backend/foo/x_test.py")
    assert _is_scanned("autobot-backend/foo/test_x.py")
    assert _is_scanned("autobot-slm-backend/conftest.py")
    assert _is_scanned("autobot-backend/tests/helpers/_fake_redis.py")
    assert _is_scanned("autobot-backend/testkit/fake_result.py")
    # contrast: production code, and a non-python file under a test dir
    assert not _is_scanned("autobot-backend/foo/service.py")
    assert not _is_scanned("autobot-backend/tests/data.json")


def test_a_checkout_under_a_directory_named_tests_does_not_widen_the_scan(tmp_path: Path) -> None:
    """The directory test reads the REPO-RELATIVE path; an absolute prefix named `tests` must not leak in (#18972)."""
    checkout = tmp_path / "tests" / ".worktrees" / "wt"
    (checkout / "autobot-backend" / "foo").mkdir(parents=True)
    (checkout / "autobot-backend" / "foo" / "service.py").write_text("X = 1\n", encoding="utf-8")
    (checkout / "autobot-backend" / "foo" / "x_test.py").write_text("X = 1\n", encoding="utf-8")
    make_repo(checkout)
    git(checkout, "add", "-A")
    assert _population(checkout) == ["autobot-backend/foo/x_test.py"]


def test_the_scan_is_not_vacuous() -> None:
    """Bind the floor to the scan's reach, never to the finding count (it is zero)."""
    assert len(REACH.examined(repo_root())) > 2000


def test_no_new_hand_rolled_redis_pipeline() -> None:
    new = sorted(_found() - set(ALLOWLIST))
    assert not new, (
        f"#18991: {new} define a Redis pipeline double by hand. Use {CANONICAL} "
        f"(FakePipeline / FakeAsyncPipeline); pass opt-ins through its constructor."
    )


def test_every_allowlist_entry_still_matches() -> None:
    stale = sorted(set(ALLOWLIST) - _found())
    assert not stale, f"stale allowlist entries (class gone or migrated); delete these lines: {stale}"


def test_the_allowlist_only_shrinks_and_every_entry_has_a_reason() -> None:
    assert len(ALLOWLIST) <= FROZEN_TOTAL, f"{len(ALLOWLIST)} entries exceeds the frozen {FROZEN_TOTAL}"
    assert all(reason.strip() for reason in ALLOWLIST.values())


def test_a_reintroduced_hand_rolled_double_is_found_in_a_scanned_path() -> None:
    """The guard's own proof: a copy of the old shape, at a scanned path, is a finding the allowlist lacks."""
    rel = "autobot-backend/services/x_test.py"
    assert _is_scanned(rel)
    keys = finding_keys(rel, _HAND_ROLLED)
    assert keys == [f"{rel}::<module>::_FakePipeline"]
    assert set(keys) - set(ALLOWLIST), "the baseline must not already excuse it"
