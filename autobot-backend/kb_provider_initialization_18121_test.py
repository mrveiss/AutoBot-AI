#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No knowledge-base provider may hand out an uninitialized instance (#18121).

``KnowledgeBaseCore.initialize()`` is what creates the vector store and must be awaited
after construction (``knowledge/base.py:147``). An instance that skipped it has
``initialized is False``, and the basic search path calls ``ensure_initialized()``
(``knowledge/search_components/basic_vector_search.py``), which raises. Every call site
of these providers catches ``Exception`` into a warning and substitutes an empty result,
so the breakage reads as "the knowledge base had nothing to say" — which is why it
survived in eight mounted endpoints unnoticed.

The assertions are static (AST over the source) on purpose: importing these modules pulls
in FastAPI, ChromaDB and Redis, and the property under test is structural — *where* the
instance comes from — not runtime behaviour.
"""

import ast
import pathlib

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_DEPENDENCIES = _REPO / "autobot-backend" / "dependencies.py"
_RESOURCE_FACTORY = _REPO / "autobot-backend" / "utils" / "resource_factory.py"


def _parse(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _find_function(tree: ast.Module, name: str, *, cls: str | None = None):
    """Return the (async) function `name`, optionally inside class `cls`."""
    scopes = [tree]
    if cls is not None:
        scopes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls]
        assert scopes, f"class {cls} not found"
    for scope in scopes:
        for node in scope.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
    return None


def _called_names(node: ast.AST) -> set[str]:
    """Every callee name reachable in `node`, bare or attribute-qualified."""
    names: set[str] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _constructs_knowledge_base(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id == "KnowledgeBase":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "KnowledgeBase":
                return True
    return False


@pytest.mark.parametrize("provider", ["get_knowledge_base", "get_cached_knowledge_base"])
def test_dependency_provider_is_async(provider: str) -> None:
    """A sync provider cannot await initialize(), so it can only return a broken instance."""
    fn = _find_function(_parse(_DEPENDENCIES), provider)
    assert fn is not None, f"dependencies.{provider} not found"
    assert isinstance(fn, ast.AsyncFunctionDef), (
        f"dependencies.{provider} must be `async def`: a synchronous provider cannot await "
        "KnowledgeBase.initialize(), so every instance it returns has initialized is False"
    )


@pytest.mark.parametrize("provider", ["get_knowledge_base", "get_cached_knowledge_base"])
def test_dependency_provider_does_not_construct(provider: str) -> None:
    fn = _find_function(_parse(_DEPENDENCIES), provider)
    assert fn is not None, f"dependencies.{provider} not found"
    assert not _constructs_knowledge_base(fn), (
        f"dependencies.{provider} constructs a KnowledgeBase directly; it must resolve the "
        "already-initialized instance through knowledge_factory instead"
    )


def test_dependency_provider_delegates_to_the_canonical_factory() -> None:
    tree = _parse(_DEPENDENCIES)
    live = _find_function(tree, "get_knowledge_base")
    assert live is not None, "dependencies.get_knowledge_base not found"
    assert "get_or_create_knowledge_base" in _called_names(live), (
        "dependencies.get_knowledge_base must return the app-state instance via "
        "knowledge_factory.get_or_create_knowledge_base"
    )
    cached = _find_function(tree, "get_cached_knowledge_base")
    assert cached is not None, "dependencies.get_cached_knowledge_base not found"
    delegates = _called_names(cached)
    assert "get_knowledge_base" in delegates or "get_or_create_knowledge_base" in delegates, (
        "dependencies.get_cached_knowledge_base must resolve the same instance as "
        "get_knowledge_base — app.state is already the cache"
    )


def test_resource_factory_does_not_construct_or_poison_app_state() -> None:
    """#18121: this provider also *wrote* its uninitialized instance to app.state.

    That is worse than returning it: app.state.knowledge_base is the store every
    api/knowledge*.py route reads, so one call here would break knowledge search for the
    whole process until restart.
    """
    fn = _find_function(_parse(_RESOURCE_FACTORY), "get_knowledge_base", cls="ResourceFactory")
    assert fn is not None, "ResourceFactory.get_knowledge_base not found"
    assert not _constructs_knowledge_base(fn), "ResourceFactory.get_knowledge_base constructs a KnowledgeBase directly"

    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Assign):
            continue
        for target in sub.targets:
            if isinstance(target, ast.Attribute) and target.attr == "knowledge_base":
                pytest.fail(
                    "ResourceFactory.get_knowledge_base assigns app.state.knowledge_base; only "
                    "knowledge_factory, which initializes before returning, may write that store"
                )

    assert _called_names(fn) & {
        "get_or_create_knowledge_base",
        "get_knowledge_base_async",
    }, "ResourceFactory.get_knowledge_base must delegate to knowledge_factory"


def test_canonical_factories_still_initialize_before_returning() -> None:
    """The delegation above is only safe while the factories it targets still initialize.

    Without this, a later change inside knowledge_factory could silently reintroduce the
    defect everywhere at once, and the tests above would still pass.
    """
    factory = _REPO / "autobot-backend" / "knowledge_factory.py"
    tree = _parse(factory)
    for name in ("_create_new_knowledge_base", "get_knowledge_base_async"):
        fn = _find_function(tree, name)
        assert fn is not None, f"knowledge_factory.{name} not found"
        assert "initialize" in _called_names(fn), (
            f"knowledge_factory.{name} no longer calls initialize(); every provider that "
            "delegates to it would start handing out uninitialized instances"
        )
