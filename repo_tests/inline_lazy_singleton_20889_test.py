# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``lazy_singleton(X)`` is a factory: build it once at module level (#20889).

Three shapes defeat it, each a defect found in this tree:

* ``lazy_singleton(X)()`` / ``lazy_singleton(X).attr`` -- uses a function as the instance, or
  builds a fresh factory (so a fresh instance) per call;
* ``lazy_singleton(X)`` inside a function or lambda body -- the same fresh factory per call,
  one step removed;
* ``WorkItemService()`` (and the other accessor-managed classes) constructed outside the
  accessors -- a second instance next to the shared one.

Imports are resolved per file from the AST, so ``from ... import x as y`` aliases are seen, and
a module alias (``sf.lazy_singleton``) is matched by the fixed attribute name. Test files may build factories inside test bodies (that is how the
factory itself is tested) and construct services directly, so only the first shape applies there.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_FACTORY_MODULE = "autobot_shared.singleton_factory"
_FACTORIES = frozenset({"lazy_singleton", "async_lazy_singleton"})

#: Classes whose one shared instance lives in ``llc/services/accessors.py``.
_MANAGED = frozenset(
    {"WorkItemService", "BudgetService", "AgentWikiService", "AttachmentService", "WorkProductService"}
)

#: A factory built inside a function on purpose, with the reason.
_FACTORY_IN_FUNCTION_ALLOWED = {
    "autobot_shared/credential_gated_registry.py": "builds one factory per registry kind and returns it",
    "autobot-backend/llc/deps.py": "the keyed registry builds one factory per class under a lock",
    "autobot-backend/knowledge/connectors/credential_store.py": "reset_credential_store rebinds the module singleton",
}
#: A managed class constructed directly on purpose, with the reason.
_CONSTRUCTION_ALLOWED = {
    "autobot-backend/llc/services/accessors.py": "the home of the shared instances",
    "autobot-backend/llc/deps.py": "the keyed registry builds the instances",
    "autobot-backend/llc/services/board.py": "WorkItemService(activity_log=...) takes a per-call argument",
}

_ROOT = repo_root()
_ROOTS = (
    ".claude",
    "autobot-backend",
    "autobot-infrastructure",
    "autobot-npu-worker",
    "autobot-slm-backend",
    "autobot_shared",
    "libs",
    "pipeline-scripts",
    "plugins",
    "repo_tests",
    "scripts",
    "tools",
)


def _tracked_python(root: Path = _ROOT) -> list[str]:
    """Tracked Python files; empty on an empty tree so the reach floor can fire."""
    try:
        return tracked_paths(root, *(f"{r}/*.py" for r in _ROOTS))
    except EmptyEnumeration:
        return []


REACH = declare(
    "inline-lazy-singleton",
    discover=_tracked_python,
    floor=8144,  # mid-window: population 8144, window (8144, 8144)
    what="tracked python files",
    roots=_ROOTS,
)


class _Names:
    """What this file's imports bind: aliased factory functions and managed classes."""

    def __init__(self, tree: ast.AST) -> None:
        self.factories: set[str] = set()
        self.managed: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self._from(node)
        for node in ast.walk(tree):  # ``S = WorkItemService`` makes ``S()`` a construction too
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and self._is_managed(node.value.id):
                self.managed.update(t.id for t in node.targets if isinstance(t, ast.Name))

    def _is_managed(self, name: str) -> bool:
        return name in self.managed or name in _MANAGED

    def _from(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        for a in node.names:
            bound = a.asname or a.name
            if mod == _FACTORY_MODULE and a.name in _FACTORIES:
                self.factories.add(bound)
            elif a.name in _MANAGED:
                self.managed.add(bound)

    def is_factory_func(self, func: ast.AST) -> bool:
        if isinstance(func, ast.Name):
            return func.id in self.factories or func.id in _FACTORIES
        # ``sf.lazy_singleton`` / ``autobot_shared.singleton_factory.lazy_singleton``: whatever the
        # module is bound to, the attribute name is fixed, so a module alias needs no resolving.
        return isinstance(func, ast.Attribute) and func.attr in _FACTORIES

    def is_factory_call(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Call) and self.is_factory_func(node.func)

    def is_managed_ctor(self, node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in self.managed or func.id in _MANAGED
        return isinstance(func, ast.Attribute) and func.attr in _MANAGED


class _Scan(ast.NodeVisitor):
    def __init__(self, names: _Names) -> None:
        self.names = names
        self.depth = 0
        self.inline: list[int] = []
        self.in_function: list[int] = []
        self.constructed: list[int] = []

    def _nested(self, node: ast.AST) -> None:
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    visit_FunctionDef = visit_AsyncFunctionDef = visit_Lambda = _nested

    def visit_Call(self, node: ast.Call) -> None:
        if self.names.is_factory_call(node.func):
            self.inline.append(node.lineno)
        if self.names.is_factory_call(node) and self.depth:
            self.in_function.append(node.lineno)
        if self.names.is_managed_ctor(node):
            self.constructed.append(node.lineno)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if self.names.is_factory_call(node.value):
            self.inline.append(node.lineno)
        self.generic_visit(node)


def scan(source: str) -> _Scan:
    tree = parse_cache.parse(source)
    result = _Scan(_Names(tree))
    result.visit(tree)
    return result


def inline_uses(source: str) -> list[int]:
    """Lines where a factory call is itself called or attribute-accessed."""
    return sorted(scan(source).inline)


def in_function_uses(source: str) -> list[int]:
    """Lines where a factory is built inside a function or lambda body."""
    return sorted(scan(source).in_function)


def direct_constructions(source: str) -> list[int]:
    """Lines where an accessor-managed class is constructed."""
    return sorted(scan(source).constructed)


def _is_test_path(rel: str) -> bool:
    base = rel.rsplit("/", 1)[-1]
    return (
        base.startswith("test_")
        or base.endswith("_test.py")
        or "test_support" in base
        or base == "conftest.py"
        or "/tests/" in f"/{rel}"
    )


def test_control_strings_are_detected():
    """The detectors must flag the bad shapes and pass the good ones."""
    assert inline_uses("x = lazy_singleton(Svc)()") == [1]
    assert inline_uses("x = lazy_singleton(Svc).attr") == [1]
    assert inline_uses("async def f():\n    return await async_lazy_singleton(Svc)()") == [2]
    assert inline_uses("x = mod.lazy_singleton(Svc)()") == [1]
    assert inline_uses("from autobot_shared.singleton_factory import lazy_singleton as ls\nx = ls(Svc)()") == [2]
    assert inline_uses("import autobot_shared.singleton_factory as sf\nx = sf.lazy_singleton(Svc)()") == [2]
    assert inline_uses("from autobot_shared import singleton_factory as sf\nx = sf.lazy_singleton(Svc).a") == [2]
    assert inline_uses("get_svc = lazy_singleton(Svc)\nx = get_svc()") == []
    assert inline_uses("get_svc = lazy_singleton(lambda: Svc())") == []


def test_control_strings_for_a_factory_built_in_a_function():
    assert in_function_uses("def f():\n    return lazy_singleton(Svc)") == [2]
    assert in_function_uses("async def f():\n    g = async_lazy_singleton(Svc)") == [2]
    assert in_function_uses("f = lambda: lazy_singleton(Svc)") == [1]
    assert in_function_uses("class C:\n    def m(self):\n        return lazy_singleton(Svc)") == [3]
    src = "from autobot_shared.singleton_factory import lazy_singleton as ls\ndef f():\n    return ls(Svc)"
    assert in_function_uses(src) == [3]
    assert in_function_uses("get = lazy_singleton(Svc)\nclass C:\n    g = lazy_singleton(Svc)") == []


def test_control_strings_for_a_direct_construction():
    assert direct_constructions("x = WorkItemService()") == [1]
    assert direct_constructions("async def f():\n    return await BudgetService().check()") == [2]
    assert direct_constructions("x = mod.AgentWikiService()") == [1]
    assert direct_constructions("from m import AttachmentService as AS\nx = AS()") == [2]
    assert direct_constructions("x = WorkProductService()") == [1]
    assert direct_constructions("S = WorkItemService\nx = S()") == [2]
    assert direct_constructions("def f():\n    S = BudgetService\n    return S()") == [3]
    assert direct_constructions("x = get_work_item_service()") == []
    assert direct_constructions("x = OtherService()") == []


def _tracked_sources() -> list[tuple[str, str]]:
    sources = []
    for rel in REACH.examined(_ROOT):
        text = (_ROOT / rel).read_text(encoding="utf-8")
        if "lazy_singleton" in text or any(c in text for c in _MANAGED):
            sources.append((rel, text))
    return sources


def test_no_inline_lazy_singleton_use():
    offenders = [f"{rel}:{n}" for rel, text in _tracked_sources() for n in inline_uses(text)]
    assert not offenders, "lazy_singleton(...) used inline; build the factory once at module level: " + ", ".join(
        offenders
    )


def test_no_factory_built_inside_a_function():
    offenders = [
        f"{rel}:{n}"
        for rel, text in _tracked_sources()
        if not _is_test_path(rel) and rel not in _FACTORY_IN_FUNCTION_ALLOWED
        for n in in_function_uses(text)
    ]
    assert not offenders, "lazy_singleton(...) built in a function body (a fresh factory per call): " + ", ".join(
        offenders
    )


def test_no_accessor_managed_class_constructed_directly():
    offenders = [
        f"{rel}:{n}"
        for rel, text in _tracked_sources()
        if not _is_test_path(rel) and rel not in _CONSTRUCTION_ALLOWED
        for n in direct_constructions(text)
    ]
    assert not offenders, "constructed directly; use llc.services.accessors.get_*: " + ", ".join(offenders)
