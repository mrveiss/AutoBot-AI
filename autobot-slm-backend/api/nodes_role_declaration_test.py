# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Assigning a role through the UI must declare it on the node (#14552).

"Assign Role Manually" wrote a `NodeRole` row and nothing else. `Node.roles`
was left untouched, which did not matter until deploy groups became
declaration-gated (#14513): `_strip_undeclared_privileged_groups` reads
`Node.roles` as the sole record of operator intent.

After that, a role assigned through the supported UI counted as UNDECLARED. The
group was stripped, the update playbook's tasks for it never fired, and the
component silently never installed — while the admin saw the assignment
succeed. `api/npu.py` already wrote `node.roles` for its dedicated NPU modal,
which is why npu-worker alone never showed the problem.

The function is AST-extracted and executed rather than imported, following
`nodes_test.py`: importing `api/nodes.py` registers FastAPI routes.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

_NODES_PY = Path(__file__).parent / "nodes.py"
_WANTED = {"_declare_role_on_node"}


def _load() -> dict:
    tree = ast.parse(_NODES_PY.read_text(encoding="utf-8"), filename=str(_NODES_PY))
    wanted = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name in _WANTED]
    assert len(wanted) == len(_WANTED), (
        f"expected {sorted(_WANTED)} in {_NODES_PY}, found {sorted(n.name for n in wanted)} — rename tracking broke"
    )
    module = ast.Module(body=wanted, type_ignores=[])
    ast.fix_missing_locations(module)
    # `select(Node).where(Node.node_id == ...)` must be constructible: the query
    # object is handed straight to the fake session, so only its shape matters.
    class _Query:
        def where(self, *_a, **_k):
            return self

    namespace: dict = {
        "select": lambda *_a, **_k: _Query(),
        "Node": SimpleNamespace(node_id=object()),
        "logger": SimpleNamespace(info=lambda *_a, **_k: None),
        "AsyncSession": object,
    }
    exec(compile(module, filename=str(_NODES_PY), mode="exec"), namespace)  # noqa: S102
    return namespace


_declare_role_on_node = _load()["_declare_role_on_node"]


class _FakeDb:
    """Minimal stand-in: the function only executes a select and reads one row."""

    def __init__(self, node):
        self._node = node

    async def execute(self, _query):
        return SimpleNamespace(scalar_one_or_none=lambda: self._node)


def _run(node, role_name):
    asyncio.run(_declare_role_on_node(_FakeDb(node), "node-under-test", role_name))
    return node


def test_assigning_a_role_declares_it():
    """The #14552 regression: the assignment must reach `Node.roles`."""
    node = _run(SimpleNamespace(node_id="node-under-test", roles=["vnc"]), "frontend")

    assert "frontend" in node.roles, (
        "a manually assigned role never reached Node.roles, so the deploy group is stripped "
        "and the component silently never installs (#14552)"
    )
    assert "vnc" in node.roles, "existing declared roles were discarded"


def test_assigning_twice_does_not_duplicate():
    node = _run(SimpleNamespace(node_id="node-under-test", roles=["frontend"]), "frontend")

    assert node.roles.count("frontend") == 1


def test_a_node_with_no_roles_yet_is_handled():
    """`roles` is nullable, and `None` must not raise."""
    node = _run(SimpleNamespace(node_id="node-under-test", roles=None), "ai-stack")

    assert node.roles == ["ai-stack"]


def test_a_missing_node_is_a_no_op_not_a_crash():
    """The caller already 404s on an unknown node; this must not raise first."""
    asyncio.run(_declare_role_on_node(_FakeDb(None), "gone", "frontend"))
