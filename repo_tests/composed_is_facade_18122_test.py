# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`knowledge/_composed.py` is a facade over `knowledge_factory` (#18122, slice S2).

Static half: by AST, `_composed` keeps no KnowledgeBase global and builds none.
Runtime half: with a stub `knowledge_base.KnowledgeBase` and stub mixin modules (so no
redis/llama_index/chromadb is imported), the facade returns the factory's instance,
raises when the factory has none, and ignores `force_new`. Each runtime test names the
line whose reversion makes it fail; the contrast fixtures show the matcher and the
stubs are not what makes it pass.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import logging
import sys
import types

import pytest
from repo_tests._paths import repo_root

import knowledge_factory as kf

COMPOSED = "autobot-backend/knowledge/_composed.py"
_MIXIN_MODULES = {
    "base": "KnowledgeBaseCore",
    "bulk": "BulkOperationsMixin",
    "categories": "CategoriesMixin",
    "collections": "CollectionsMixin",
    "documents": "DocumentsMixin",
    "facts": "FactsMixin",
    "index": "IndexMixin",
    "metadata": "MetadataMixin",
    "relations": "RelationsMixin",
    "search": "SearchMixin",
    "stats": "StatsMixin",
    "suggestions": "SuggestionsMixin",
    "tags": "TagsMixin",
    "versioning": "VersioningMixin",
}


def _holds_or_builds_a_knowledge_base(tree: ast.Module) -> list[str]:
    """Module-level KnowledgeBase-annotated names, and any `KnowledgeBase(` call."""
    found = []
    for stmt in tree.body:
        if isinstance(stmt, ast.AnnAssign) and "KnowledgeBase" in ast.unparse(stmt.annotation):
            found.append(f"global:{ast.unparse(stmt.target)}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "KnowledgeBase":
            found.append(f"construct:line {node.lineno}")
    return found


def test_composed_holds_and_builds_nothing() -> None:
    source = (repo_root() / COMPOSED).read_text(encoding="utf-8")
    assert _holds_or_builds_a_knowledge_base(ast.parse(source)) == []


@pytest.mark.parametrize(
    "source,expected",
    [
        ('_kb: "KnowledgeBase | None" = None\n', ["global:_kb"]),
        ("async def f():\n    return KnowledgeBase()\n", ["construct:line 2"]),
        ("class KnowledgeBase:\n    pass\n\n\nasync def f(kb: KnowledgeBase):\n    return kb\n", []),
    ],
)
def test_the_matcher_flags_a_global_and_a_construction_but_not_the_class(source, expected) -> None:
    """Contrast: the AST matcher is not vacuous, and the class definition is not a hit."""
    assert _holds_or_builds_a_knowledge_base(ast.parse(source)) == expected


class _Stub:
    constructed = 0
    outcome = True

    def __init__(self) -> None:
        type(self).constructed += 1
        self.initialized = False

    async def initialize(self) -> bool:
        self.initialized = bool(type(self).outcome)
        return type(self).outcome


@pytest.fixture
def composed(monkeypatch):
    """The real `_composed.py` source, loaded against stub mixins and a stub KnowledgeBase."""
    _Stub.constructed, _Stub.outcome = 0, True
    for mod, cls in _MIXIN_MODULES.items():
        stub = types.ModuleType(f"knowledge.{mod}")
        setattr(stub, cls, type(cls, (), {}))
        monkeypatch.setitem(sys.modules, f"knowledge.{mod}", stub)
    kb_mod = types.ModuleType("knowledge_base")
    kb_mod.KnowledgeBase = _Stub
    monkeypatch.setitem(sys.modules, "knowledge_base", kb_mod)
    monkeypatch.setattr(kf, "_knowledge_base_instance", None)
    monkeypatch.setattr(kf, "_last_kb_init_failure", 0.0)
    monkeypatch.setattr(kf, "_knowledge_base_lock", asyncio.Lock())
    monkeypatch.setattr(kf, "_adopt_legacy_facts", lambda kb: None)
    spec = importlib.util.spec_from_file_location("_composed_facade_probe", repo_root() / COMPOSED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_returns_the_factorys_instance(composed) -> None:
    """Reverting the delegation to `get_knowledge_base_async` -> a private instance."""
    kb = await composed.get_knowledge_base()
    assert kb is kf.peek_knowledge_base()
    assert await composed.get_knowledge_base() is kb
    assert _Stub.constructed == 1


async def test_raises_when_the_factory_returns_none(composed) -> None:
    """Reverting the `is None` check -> None leaks to ~44 callers that never test for it."""
    _Stub.outcome = False
    with pytest.raises(RuntimeError, match="Failed to initialize knowledge base"):
        await composed.get_knowledge_base()
    # Cooldown now active (owner D2): still an error, and no second construction.
    with pytest.raises(RuntimeError):
        await composed.get_knowledge_base()
    assert _Stub.constructed == 1


async def test_force_new_warns_and_returns_the_shared_instance(composed, caplog) -> None:
    """Reverting the `force_new` branch -> a second build (owner D3)."""
    first = await composed.get_knowledge_base()
    with caplog.at_level(logging.WARNING):
        again = await composed.get_knowledge_base(force_new=True)
    assert again is first
    assert _Stub.constructed == 1
    assert any("force_new" in r.getMessage() for r in caplog.records)


async def test_control_without_force_new_does_not_warn(composed, caplog) -> None:
    """Contrast: the warning in the test above comes from `force_new`, not from creation."""
    with caplog.at_level(logging.WARNING):
        await composed.get_knowledge_base()
    assert not any("force_new" in r.getMessage() for r in caplog.records)


async def test_reset_clears_the_factorys_store_and_the_next_call_rebuilds(composed) -> None:
    """Reverting the delegation to `knowledge_factory.reset_knowledge_base` -> stale instance."""
    first = await composed.get_knowledge_base()
    composed.reset_knowledge_base()
    assert kf.peek_knowledge_base() is None
    assert await composed.get_knowledge_base() is not first
    assert _Stub.constructed == 2


async def test_reset_with_an_app_clears_the_projection_and_rebuilds_one_instance(composed) -> None:
    """Reverting `app` in the reset -> app.state keeps the old KB and the two paths diverge."""
    app = types.SimpleNamespace(state=types.SimpleNamespace())
    first = await kf.get_or_create_knowledge_base(app)
    assert app.state.knowledge_base is first is kf.peek_knowledge_base()
    composed.reset_knowledge_base(app)
    assert kf.peek_knowledge_base() is None
    assert app.state.knowledge_base is None
    second = await kf.get_or_create_knowledge_base(app)
    assert second is not first
    assert second is kf.peek_knowledge_base() is app.state.knowledge_base
    assert await composed.get_knowledge_base() is second


async def test_reset_without_an_app_is_not_served_stale_by_the_app_path(composed) -> None:
    """Contrast: the app-free reset leaves the projection stale, but the read side refuses it.

    Reverting the `kb is not singleton` gates in `_ready_app_state_kb` -> the app path
    returns `first` while the app-free path builds a second instance.
    """
    app = types.SimpleNamespace(state=types.SimpleNamespace())
    first = await kf.get_or_create_knowledge_base(app)
    composed.reset_knowledge_base()
    assert kf.peek_knowledge_base() is None
    assert app.state.knowledge_base is first  # app-free reset does not touch the projection
    second = await kf.get_or_create_knowledge_base(app)
    assert second is not first
    assert second is kf.peek_knowledge_base() is app.state.knowledge_base
    assert await composed.get_knowledge_base() is second
    assert _Stub.constructed == 2


def test_the_facade_keeps_its_module_level_names(composed) -> None:
    """12 test files patch `knowledge.get_knowledge_base` by name; the names must stay exported."""
    for name in ("get_knowledge_base", "reset_knowledge_base", "KnowledgeBase"):
        assert hasattr(composed, name)
