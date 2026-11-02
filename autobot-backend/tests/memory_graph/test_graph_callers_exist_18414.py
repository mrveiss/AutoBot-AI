# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #18414 / #18140: every method called on a memory graph (or memory
provider) receiver must exist on the real class.

A bare AsyncMock accepts any attribute, so a call to a method the graph does not
have passed its tests and raised AttributeError in production. This guard reads
the callers and checks them against ``dir()`` of the real class.

Blind spots (what an empty result does NOT prove):
- receivers it cannot resolve: a graph passed through an unannotated parameter, a
  container, a lambda, or a name other than ``memory_graph`` / ``_memory_graph`` or a
  local bound directly from the class or a listed factory;
- dynamic dispatch: ``getattr(graph, name)(...)``, ``**`` forwarding, ``functools.partial``;
- attribute access that is not a call (``graph.method`` passed as a callback);
- argument mismatches: it checks that the method exists, not that the arguments fit;
- non-production code (``*_test.py``, ``tests/``) and non-Python callers;
- the provider check covers only ``memory/manager.py``'s ``built_in`` / ``external``.

Because a broken scanner reads as a clean result, the population floors below fail the
test when it examined less than it should.
"""

import ast
from pathlib import Path

from autobot_memory_graph import AutoBotMemoryGraph
from services.memory.memory_provider_interface import MemoryProvider

BACKEND = Path(__file__).resolve().parents[2]
GRAPH_NAMES = {"memory_graph", "_memory_graph"}
GRAPH_FACTORIES = {"AutoBotMemoryGraph", "get_memory_graph", "_get_memory_graph_or_none", "resolve_memory_graph"}
PROVIDER_NAMES = {"built_in", "external"}
PROVIDER_FILES = {"memory/manager.py"}
SKIP_PARTS = {"node_modules", ".venv", "venv", "__pycache__"}


def _callee(node: ast.AST) -> str | None:
    """Name of the function being called, through an await."""
    if isinstance(node, ast.Await):
        node = node.value
    if isinstance(node, ast.Call):
        func = node.func
        return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    return None


def _graph_locals(tree: ast.AST) -> set[str]:
    """Local names bound from the graph class or a factory returning it."""
    names = set(GRAPH_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _callee(node.value) in GRAPH_FACTORIES:
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.arg) and node.annotation is not None:
            if "AutoBotMemoryGraph" in ast.unparse(node.annotation):
                names.add(node.arg)
    return names


def _receiver(node: ast.Attribute) -> str | None:
    base = node.value
    return base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)


def scan_calls(source: str, receivers: set[str], cls: type, include_locals: bool) -> tuple[list[tuple[str, int]], int]:
    """((method, line) for each call the class lacks, number of receiver calls examined)."""
    tree = ast.parse(source)
    names = _graph_locals(tree) | receivers if include_locals else receivers
    have = set(dir(cls))
    found, examined = [], 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and _receiver(node.func) in names:
            examined += 1
            if node.func.attr not in have:
                found.append((node.func.attr, node.lineno))
    return found, examined


def missing_calls(source: str, receivers: set[str], cls: type, include_locals: bool) -> list[tuple[str, int]]:
    """(method, line) for each `receiver.method(...)` call the class lacks."""
    return scan_calls(source, receivers, cls, include_locals)[0]


# Floors set from the real counts when written (2026-10-12: 2,850 production files read,
# 207 graph calls, 16 provider calls), with headroom. They guard the scanner, not the code.
MIN_FILES_SCANNED = 2000
MIN_GRAPH_CALLS = 150
MIN_PROVIDER_CALLS = 12


def _production_files(root: Path):
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if SKIP_PARTS & set(path.parts) or path.name.endswith("_test.py") or rel.startswith("tests/"):
            continue
        yield rel, path


def _scan_tree(root: Path) -> tuple[list, int, int]:
    """(missing calls, production files read, graph calls examined) under ``root``."""
    bad, files, calls = [], 0, 0
    for rel, path in _production_files(root):
        files += 1
        text = path.read_text(encoding="utf-8")
        if "memory_graph" not in text and "AutoBotMemoryGraph" not in text:
            continue
        missing, examined = scan_calls(text, GRAPH_NAMES, AutoBotMemoryGraph, True)
        bad += [(rel, m, line) for m, line in missing]
        calls += examined
    return bad, files, calls


def test_every_call_on_a_graph_receiver_exists():
    """Production callers only call methods AutoBotMemoryGraph has."""
    bad, files, calls = _scan_tree(BACKEND)
    assert files >= MIN_FILES_SCANNED, f"scanner read only {files} files; it did not look"
    assert calls >= MIN_GRAPH_CALLS, f"scanner found only {calls} graph calls; it did not look"
    assert not bad, f"calls to methods AutoBotMemoryGraph does not have: {bad}"


def test_every_call_on_a_provider_receiver_exists():
    """The manager only calls methods the MemoryProvider interface declares."""
    bad, calls = [], 0
    for rel in PROVIDER_FILES:
        text = (BACKEND / rel).read_text(encoding="utf-8")
        missing, examined = scan_calls(text, PROVIDER_NAMES, MemoryProvider, False)
        bad += [(rel, m, line) for m, line in missing]
        calls += examined
    assert calls >= MIN_PROVIDER_CALLS, f"scanner found only {calls} provider calls; it did not look"
    assert not bad, f"calls to methods MemoryProvider does not have: {bad}"


def test_guard_flags_the_defects_it_exists_for():
    """Contrast: the pre-fix callers are flagged, so an empty result is not 'did not look'."""
    old = (
        "async def f(self):\n"
        "    await self._memory_graph.traverse_relations(entity_name='h', depth=2)\n"
        "    graph = AutoBotMemoryGraph()\n"
        "    await graph.add_or_update_entity(name='x')\n"
        "    await graph.add_relation(source='a', target='b')\n"
    )
    flagged = {m for m, _ in missing_calls(old, GRAPH_NAMES, AutoBotMemoryGraph, True)}
    assert flagged == {"traverse_relations", "add_or_update_entity", "add_relation"}
    ok = "async def f(self):\n    await self._memory_graph.get_related_entities('h')\n"
    assert missing_calls(ok, GRAPH_NAMES, AutoBotMemoryGraph, True) == []


def test_population_floors_fail_on_an_empty_tree(tmp_path):
    """Contrast: pointed at nothing, the scanner finds no defects AND trips the floors."""
    bad, files, calls = _scan_tree(tmp_path)
    assert bad == []
    assert files < MIN_FILES_SCANNED and calls < MIN_GRAPH_CALLS
