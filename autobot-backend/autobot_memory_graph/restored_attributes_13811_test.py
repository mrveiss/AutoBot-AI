# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attributes read by ``entities.py`` must be assigned by the core (#13811).

#716 split ``autobot_memory_graph.py`` into this package and dropped two
``__init__`` assignments while their readers came across intact:

    self.knowledge_base = None            ->  read at entities.py x3
    self.search_cache = LRUCache(1000)    ->  cleared at entities.py x3

A missing attribute is not a falsy one. ``if self.knowledge_base:`` was written to
take a disabled branch and instead raised ``AttributeError``, and because
``_store_entity_in_redis`` writes to Redis *before* the guard, ``create_entity``
persisted the entity and then failed -- HTTP 500 over a row that exists, so a
client retrying on 500 duplicates it.

## Why this file does not reuse the neighbouring fixture

``entity_vocabulary_test.py`` builds the same graph and then assigns
``graph.knowledge_base = None`` itself. That line is why the suite stayed green
over a production crash: the test supplied the state the constructor owed. The
fixture here deliberately assigns neither attribute, so what is asserted is the
constructor's output and not the fixture's.

## Why the guard is a reachability check, not a string search

`test_every_core_attribute_entities_reads_is_assigned_by_init` compares two AST-derived
sets -- ``self.X`` loads in ``entities.py`` against ``self.X`` stores in
``AutoBotMemoryGraphCore.__init__`` -- so it catches the *next* attribute lost the
same way, not just these two. Names resolved through the MRO (mixin methods,
properties) are excluded by the callable/property check at class level rather than
by a hand-maintained allowlist, which would need editing every time a method moved.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from autobot_memory_graph import AutoBotMemoryGraph
from autobot_memory_graph.core import AutoBotMemoryGraphCore

_ENTITIES = Path(__file__).with_name("entities.py")
_CORE = Path(__file__).with_name("core.py")


def _graph_without_hand_fed_state() -> AutoBotMemoryGraph:
    """An initialised-looking graph with mocked Redis and NOTHING else supplied.

    Mirrors ``entity_vocabulary_test._graph`` except that it assigns neither
    ``knowledge_base`` nor ``search_cache`` -- those are the constructor's job and
    are what this file exists to assert.
    """
    graph = AutoBotMemoryGraph()
    graph._initialized = True
    json_ops = Mock()
    json_ops.set = AsyncMock()
    json_ops.get = AsyncMock(return_value={})
    graph.redis_client = Mock()
    graph.redis_client.json = Mock(return_value=json_ops)
    property_graph = Mock()
    property_graph.add_node = AsyncMock()
    graph._property_graph = property_graph
    return graph


def _self_attribute_loads(path: Path) -> set[str]:
    """``self.X`` names read (not assigned) anywhere in *path*, from the AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and isinstance(node.ctx, ast.Load)
    }


def _init_assigned_attributes(path: Path) -> set[str]:
    """``self.X = ...`` names stored by ``AutoBotMemoryGraphCore.__init__``.

    Covers plain and annotated assignment; the restored lines use the annotated
    form, which ``ast.Assign`` alone does not see.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assigned: set[str] = set()
    for cls in ast.walk(tree):
        if not (isinstance(cls, ast.ClassDef) and cls.name == "AutoBotMemoryGraphCore"):
            continue
        for fn in cls.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == "__init__"):
                continue
            for node in ast.walk(fn):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                for t in targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                        assigned.add(t.attr)
    return assigned


def test_a_fresh_graph_has_both_restored_attributes() -> None:
    graph = AutoBotMemoryGraph()
    assert graph.knowledge_base is None, "knowledge_base must default to None, not be absent"
    assert hasattr(graph, "search_cache"), "search_cache was never reassigned after #716"
    graph.search_cache.clear()  # the exact call entities.py makes


def test_knowledge_base_is_injectable() -> None:
    """#13811 sanctions injection; None-by-default must not mean None-only."""
    sentinel = object()
    assert AutoBotMemoryGraphCore(knowledge_base=sentinel).knowledge_base is sentinel


@pytest.mark.asyncio
async def test_create_entity_completes_without_attributeerror() -> None:
    """The reported repro: the entity is written, then the guard raised.

    Pre-fix this raises ``RuntimeError("Entity creation failed")`` wrapping
    ``AttributeError: ... has no attribute 'knowledge_base'`` -- after the Redis
    write has already landed.
    """
    graph = _graph_without_hand_fed_state()
    entity = await graph.create_entity(
        entity_type="DECISION",
        name="ZZPROBE",
        observations=["probe"],
    )
    assert entity["name"] == "ZZPROBE"
    assert entity["type"] == "DECISION"


@pytest.mark.asyncio
async def test_the_redis_write_and_the_return_now_agree() -> None:
    """The defect's signature was a persisted row plus a failed call.

    Asserting only "no exception" would pass on an implementation that also
    skipped the write, so the write is asserted to have happened too.
    """
    graph = _graph_without_hand_fed_state()
    await graph.create_entity(entity_type="DECISION", name="ZZPROBE2", observations=["probe"])
    graph.redis_client.json().set.assert_awaited()


@pytest.mark.asyncio
async def test_the_property_graph_mirror_runs_and_carries_name_and_type() -> None:
    """#13811's third verification item, and the cause of its null-name symptom.

    ``EntityOperationsMixin.create_entity`` raised before
    ``PropertyGraphMixin.create_entity`` could mirror the entity, so a later
    ``create_relation`` auto-created a bare node and ``/api/graph-rag/path``
    returned ``{"name": null, "type": null}``. Asserting the *properties*, not
    merely that ``add_node`` was called: a mirror that runs with empty props
    reproduces the original symptom exactly.
    """
    graph = _graph_without_hand_fed_state()
    await graph.create_entity(entity_type="DECISION", name="ZZPROBE3", observations=["probe"])

    graph._property_graph.add_node.assert_awaited()
    props = graph._property_graph.add_node.await_args.kwargs.get("properties")
    if props is None:
        props = next(a for a in graph._property_graph.add_node.await_args.args if isinstance(a, dict))
    assert props["name"] == "ZZPROBE3", f"mirrored node has no name: {props}"
    assert props["type"] == "DECISION", f"mirrored node has no type: {props}"


def test_every_core_attribute_entities_reads_is_assigned_by_init() -> None:
    """Catches the next attribute dropped by a split, not just these two."""
    assigned = _init_assigned_attributes(_CORE)
    assert "redis_client" in assigned, "control failed: __init__ parser found no known attribute"
    loads = _self_attribute_loads(_ENTITIES)
    assert loads, "control failed: no self.X loads parsed out of entities.py"

    # Anything resolvable on the composed class (mixin methods, properties,
    # class attributes) is not state __init__ owes.
    missing = sorted(name for name in loads if name not in assigned and not hasattr(AutoBotMemoryGraph, name))
    assert not missing, f"entities.py reads attributes AutoBotMemoryGraphCore.__init__ never assigns: {missing}"


def test_prose_mentions_do_not_count_as_assignments() -> None:
    """Contrast fixture: the names in a docstring and a comment, assigned nowhere.

    ``grep 'self.knowledge_base'`` over this source hits twice, so a text-matching
    version of the check above would call the attribute assigned. The AST holds no
    ``Assign`` node for it, which is the distinction being asserted.
    """
    prose_only = '''
class AutoBotMemoryGraphCore:
    def __init__(self):
        """Sets self.knowledge_base = None and self.search_cache, one day."""
        # self.search_cache = LRUCache(maxsize=1000)
        self.redis_client = None
'''
    assert "self.knowledge_base = None" in prose_only, "fixture lost the string it carries"
    found = _init_assigned_attributes_from_source(prose_only)
    assert found == {"redis_client"}, f"prose registered as an assignment: {found}"


def _init_assigned_attributes_from_source(source: str) -> set[str]:
    """Source-string twin of :func:`_init_assigned_attributes`, for the fixture above."""
    tmp = ast.parse(source)
    assigned: set[str] = set()
    for cls in ast.walk(tmp):
        if not (isinstance(cls, ast.ClassDef) and cls.name == "AutoBotMemoryGraphCore"):
            continue
        for fn in cls.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == "__init__"):
                continue
            for node in ast.walk(fn):
                targets = (
                    node.targets
                    if isinstance(node, ast.Assign)
                    else ([node.target] if isinstance(node, ast.AnnAssign) else [])
                )
                for t in targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                        assigned.add(t.attr)
    return assigned
