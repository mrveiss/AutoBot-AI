# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A read-only, in-memory stand-in for the persisted code-graph collection (#21327).

``conftest`` stubs the real ``chromadb`` package for the whole suite, so a test that wants real
query behaviour needs its own collection. This one filters ``ids`` and ``metadatas`` by ``where``
(equality, ``$eq`` and ``$and``) and by ``ids``, the shapes the graph readers issue. Any write
raises, so a test that runs a query path against it also proves that path never mutates the graph.
"""

from typing import Any

PROVENANCE_ID = "code_graph::provenance"

#: A full-length commit id the sample provenance record names.
DEFAULT_COMMIT = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"  # pragma: allowlist secret


def node(node_id: str, name: str, kind: str = "function", parent: str = "", path: str = "") -> tuple[str, dict]:
    meta = {
        "record_type": "node",
        "node_kind": kind,
        "node_name": name,
        "source_path": path or node_id.rsplit(".", 1)[0].replace(".", "/") + ".py",
        "line": "1",
        "parent": parent,
    }
    return node_id, meta


def edge(source_id: str, target_id: str, target_name: str) -> tuple[str, dict]:
    meta = {
        "record_type": "edge",
        "kind": "calls",
        "source_id": source_id,
        "target_id": target_id,
        "target_name": target_name,
        "resolved": True,
        "candidate_count": 1,
        "call_line": 3,
    }
    return f"edge::{source_id}::{target_name}", meta


def provenance(commit: str = DEFAULT_COMMIT) -> tuple[str, dict]:
    return PROVENANCE_ID, {
        "record_type": "graph_provenance",
        "root_dir": "/srv/checkout/project",
        "indexed_at_commit": commit,
        "indexed_at": "2026-11-11T10:00:00+00:00",
    }


#: A small graph: ``pkg.b.caller`` calls ``pkg.a.target``, ``pkg.d.top`` calls ``pkg.b.caller``,
#: and ``helper`` is defined in two modules (an ambiguous bare name).
def sample_records(commit: str | None = DEFAULT_COMMIT) -> list[tuple[str, dict]]:
    records = [
        node("pkg.a.target", "target"),
        node("pkg.a.helper", "helper"),
        node("pkg.b.helper", "helper"),
        node("pkg.b.caller", "caller"),
        node("pkg.d.top", "top"),
        node("pkg.c.Widget", "Widget", kind="class"),
        node("pkg.c.Widget.render", "render", kind="method", parent="pkg.c.Widget"),
        edge("pkg.b.caller", "pkg.a.target", "target"),
        edge("pkg.d.top", "pkg.b.caller", "caller"),
    ]
    return records + ([provenance(commit)] if commit else [])


#: Collection methods that mutate; touching one on the fake fails the test.
_WRITE_METHODS = frozenset({"add", "upsert", "update", "delete", "modify"})


def _matches(meta: dict, where: dict | None) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_matches(meta, clause) for clause in where["$and"])
    return all(meta.get(key) == (cond["$eq"] if isinstance(cond, dict) else cond) for key, cond in where.items())


class FakeGraphCollection:
    """Records as ``(id, metadata)`` pairs; reads only."""

    def __init__(self, records: list[tuple[str, dict]] | None = None) -> None:
        self._records = list(sample_records() if records is None else records)
        self.reads = 0

    def count(self) -> int:
        return len(self._records)

    def get(self, ids: list[str] | None = None, where: dict | None = None, include: Any = None) -> dict:
        self.reads += 1
        hits = [(i, m) for i, m in self._records if (ids is None or i in ids) and _matches(m, where)]
        return {"ids": [i for i, _ in hits], "metadatas": [m for _, m in hits]}

    def __getattr__(self, name: str) -> Any:
        """Only reached for names the class does not define: a write method refuses, anything else is absent."""
        if name in _WRITE_METHODS:
            raise AssertionError("the code-graph read path attempted a write")
        raise AttributeError(name)
