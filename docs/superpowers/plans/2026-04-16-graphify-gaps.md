# Graphify Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt three techniques from Graphify into AutoBot's RAG/mesh pipeline: (A) edge provenance taxonomy, (B) Leiden community clustering for anchor seeding, and (C) tree-sitter AST code indexing.

**Architecture:** (A) Standardises the existing `origin` string column on `mesh_edges` to a typed `EdgeOrigin` literal and surfaces it through `GraphRAGService`. (B) A new `CommunityCluserer` service builds a NetworkX graph from `MeshDB.fetch_edges()`, runs Leiden, and calls `promote_to_anchor()` on cluster centroids; `MeshDB` gains `get_anchor_neighbors()` so `NeuralMeshRetriever` can seed PPR from community anchors. (C) A new `CodeIndexer` mirrors `DocIndexer`'s SHA-256 cache + ChromaDB upsert pattern but uses tree-sitter two-pass AST extraction (structural + call-graph) instead of markdown chunking.

**Tech Stack:** `tree-sitter>=0.23`, `tree-sitter-python>=0.23`, `tree-sitter-javascript>=0.23`, `networkx>=3.3`, `graspologic>=3.4` (lazy import), pytest + AsyncMock (existing)

---

## File Map

**Create:**
- `autobot-backend/services/mesh_brain/community_clusterer.py` — Leiden clustering + anchor promotion
- `autobot-backend/services/mesh_brain/community_clusterer_test.py`
- `autobot-backend/services/knowledge/code_indexer.py` — tree-sitter AST extraction + ChromaDB upsert
- `autobot-backend/services/knowledge/code_indexer_test.py`

**Modify:**
- `autobot-backend/services/mesh_brain/mesh_db.py` — add `get_anchor_neighbors()`
- `autobot-backend/services/mesh_brain/mesh_db_adapter.py` — forward `get_anchor_neighbors()`
- `autobot-backend/services/graph_rag_service.py` — add `source` provenance field to relation metadata
- `autobot-backend/requirements.txt` — add `tree-sitter`, `tree-sitter-python`, `tree-sitter-javascript`, `networkx`, `graspologic`

---

## Task 0: Create GitHub Issues + Add Dependencies

**Files:**
- Modify: `autobot-backend/requirements.txt`

- [ ] **Step 1: Create three GitHub issues**

```bash
gh issue create \
  --title "feat(mesh): standardise EdgeOrigin provenance taxonomy on mesh_edges" \
  --body "Add EdgeOrigin literal type (extracted/inferred/ambiguous) to mesh_brain and surface it in GraphRAGService relation metadata. Adopted from Graphify research — replaces ad-hoc origin strings with a typed enum." \
  --label "enhancement"

gh issue create \
  --title "feat(mesh): Leiden community clustering for anchor seeding in NeuralMeshRetriever" \
  --body "Add CommunityCluserer service: builds NetworkX graph from MeshDB.fetch_edges(), runs Leiden, promotes cluster centroids to anchors via promote_to_anchor(). Add MeshDB.get_anchor_neighbors() to satisfy NeuralMeshRetriever._AnchorDB Protocol. Adopted from Graphify research." \
  --label "enhancement"

gh issue create \
  --title "feat(knowledge): tree-sitter AST code indexer for ChromaDB" \
  --body "New CodeIndexer service: two-pass tree-sitter extraction (structural declarations + call-graph edges) for Python and JS/TS source files. Mirrors DocIndexer SHA-256 cache + ChromaDB upsert pattern. Adopted from Graphify research." \
  --label "enhancement"
```

Note the issue numbers returned — substitute `#XXXX` below.

- [ ] **Step 2: Add dependencies**

In `autobot-backend/requirements.txt`, after the `# AI/ML` block add:

```
# Graph / AST (Issue #XXXX, #XXXX, #XXXX)
networkx>=3.3
graspologic>=3.4
tree-sitter>=0.23.0
tree-sitter-python>=0.23.0
tree-sitter-javascript>=0.23.0
```

- [ ] **Step 3: Commit**

```bash
cd autobot-backend
git add requirements.txt
git commit -m "chore(deps): add networkx, graspologic, tree-sitter for mesh+AST gaps (#XXXX)"
```

---

## Task A: Edge Provenance Taxonomy (EdgeOrigin)

**Files:**
- Modify: `autobot-backend/services/graph_rag_service.py:629-672`
- Test: `autobot-backend/services/graph_rag_service_test.py`

### A1 — Failing test for `source` field in relation metadata

- [ ] **Step 1: Write failing test**

Open `autobot-backend/services/graph_rag_service_test.py` and add at the end of the file:

```python
# ============================================================================
# Task A: EdgeOrigin provenance in _create_search_result_from_entity
# ============================================================================

def test_create_search_result_includes_source_extracted():
    """source='extracted' propagates into metadata when relation has origin='extracted'."""
    rag = AsyncMock()
    graph = AsyncMock()
    graph.initialized = True
    svc = GraphRAGService(rag, graph)

    entity = {"id": "e1", "type": "module", "name": "auth", "observations": ["handles login"]}
    relation = {"type": "imports", "metadata": {"strength": 0.9, "origin": "extracted"}}

    result = svc._create_search_result_from_entity(entity, relation, "outgoing", 1.0, 2)

    assert result is not None
    assert result.metadata["source_provenance"] == "extracted"


def test_create_search_result_includes_source_inferred():
    """source='inferred' propagates when origin is absent (defaults to inferred)."""
    rag = AsyncMock()
    graph = AsyncMock()
    graph.initialized = True
    svc = GraphRAGService(rag, graph)

    entity = {"id": "e2", "type": "function", "name": "login", "observations": ["validates token"]}
    relation = {"type": "calls", "metadata": {"strength": 0.5}}

    result = svc._create_search_result_from_entity(entity, relation, "incoming", 0.8, 2)

    assert result is not None
    assert result.metadata["source_provenance"] == "inferred"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd autobot-backend
python -m pytest services/graph_rag_service_test.py::test_create_search_result_includes_source_extracted services/graph_rag_service_test.py::test_create_search_result_includes_source_inferred -v
```

Expected: `FAILED — KeyError: 'source_provenance'`

- [ ] **Step 3: Implement in `graph_rag_service.py`**

In `_create_search_result_from_entity` (line ~629), find the `return SearchResult(...)` block. Change the `metadata` dict inside it:

Old block (lines ~655-667):
```python
        return SearchResult(
            content=content,
            metadata={
                "entity_id": related_entity.get("id"),
                "entity_type": related_entity.get("type"),
                "entity_name": related_entity.get("name"),
                "source": "graph_expansion",
                "relation_type": relation.get("type"),
                "direction": direction,
                "graph_distance": max_depth,
            },
```

New block:
```python
        _origin = relation.get("metadata", {}).get("origin", "inferred")
        _provenance: str
        if _origin in ("extracted", "inferred", "ambiguous"):
            _provenance = _origin
        else:
            _provenance = "inferred"

        return SearchResult(
            content=content,
            metadata={
                "entity_id": related_entity.get("id"),
                "entity_type": related_entity.get("type"),
                "entity_name": related_entity.get("name"),
                "source": "graph_expansion",
                "source_provenance": _provenance,
                "relation_type": relation.get("type"),
                "direction": direction,
                "graph_distance": max_depth,
            },
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd autobot-backend
python -m pytest services/graph_rag_service_test.py::test_create_search_result_includes_source_extracted services/graph_rag_service_test.py::test_create_search_result_includes_source_inferred -v
```

Expected: `2 passed`

- [ ] **Step 5: Run full graph_rag test suite — no regressions**

```bash
python -m pytest services/graph_rag_service_test.py -v
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/graph_rag_service.py services/graph_rag_service_test.py
git commit -m "feat(mesh): add source_provenance field to GraphRAGService relation metadata (#XXXX)"
```

---

## Task B1: `MeshDB.get_anchor_neighbors()` + `MeshDBAdapter` forward

**Files:**
- Modify: `autobot-backend/services/mesh_brain/mesh_db.py`
- Modify: `autobot-backend/services/mesh_brain/mesh_db_adapter.py`
- Test: `autobot-backend/services/mesh_brain/mesh_db_test.py`

### B1.1 — Failing test

- [ ] **Step 1: Write failing test**

Open `autobot-backend/services/mesh_brain/mesh_db_test.py` and add at the end:

```python
# ============================================================================
# Task B1: get_anchor_neighbors
# ============================================================================

@pytest.mark.asyncio
async def test_get_anchor_neighbors_returns_anchor_nodes_adjacent_to_seeds():
    """get_anchor_neighbors returns UUIDs of anchor nodes reachable from seed_ids."""
    engine = AsyncMock()
    conn = AsyncMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=conn)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

    anchor_id = "aaaaaaaa-0000-0000-0000-000000000001"
    seed_id = "bbbbbbbb-0000-0000-0000-000000000002"

    rows = AsyncMock()
    rows.mappings.return_value.fetchall.return_value = [{"id": anchor_id}]
    conn.execute = AsyncMock(return_value=rows)

    db = MeshDB(engine)
    result = await db.get_anchor_neighbors([seed_id])

    assert result == [anchor_id]
    conn.execute.assert_called_once()
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd autobot-backend
python -m pytest services/mesh_brain/mesh_db_test.py::test_get_anchor_neighbors_returns_anchor_nodes_adjacent_to_seeds -v
```

Expected: `FAILED — AttributeError: 'MeshDB' object has no attribute 'get_anchor_neighbors'`

- [ ] **Step 3: Implement in `mesh_db.py`**

In `autobot-backend/services/mesh_brain/mesh_db.py`, add this method inside `MeshDB` after `get_neighbors()` (around line 200):

```python
    async def get_anchor_neighbors(self, seed_ids: list[str]) -> list[str]:
        """Return IDs of anchor nodes adjacent to any seed_id. Satisfies _AnchorDB Protocol (#XXXX)."""
        if not seed_ids:
            return []
        sql = text("""
            SELECT DISTINCT n.id::text
            FROM mesh_nodes n
            JOIN mesh_edges e
              ON e.from_node = n.id OR e.to_node = n.id
            WHERE (e.from_node = ANY(:seeds::uuid[])
               OR  e.to_node   = ANY(:seeds::uuid[]))
              AND n.is_anchor = TRUE
              AND n.id != ALL(:seeds::uuid[])
            """)
        async with self.engine.connect() as conn:
            rows = await conn.execute(sql, {"seeds": seed_ids})
            return [row["id"] for row in rows.mappings().fetchall()]
```

- [ ] **Step 4: Run test — expect PASS**

```bash
python -m pytest services/mesh_brain/mesh_db_test.py::test_get_anchor_neighbors_returns_anchor_nodes_adjacent_to_seeds -v
```

Expected: `1 passed`

- [ ] **Step 5: Forward in `mesh_db_adapter.py`**

In `MeshDBAdapter`, add after `get_neighbors()`:

```python
    async def get_anchor_neighbors(self, seed_ids: list[str]) -> list[str]:
        """Return IDs of anchor nodes adjacent to any seed_id (#XXXX)."""
        return await self._db.get_anchor_neighbors(seed_ids)
```

- [ ] **Step 6: Run existing mesh_db tests — no regressions**

```bash
python -m pytest services/mesh_brain/mesh_db_test.py services/mesh_brain/mesh_db_adapter_test.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add services/mesh_brain/mesh_db.py services/mesh_brain/mesh_db_adapter.py services/mesh_brain/mesh_db_test.py
git commit -m "feat(mesh): add get_anchor_neighbors() to MeshDB + MeshDBAdapter (#XXXX)"
```

---

## Task B2: Leiden Community Clusterer

**Files:**
- Create: `autobot-backend/services/mesh_brain/community_clusterer.py`
- Create: `autobot-backend/services/mesh_brain/community_clusterer_test.py`

### B2.1 — Tests first

- [ ] **Step 1: Create the test file**

Create `autobot-backend/services/mesh_brain/community_clusterer_test.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for CommunityCluserer (#XXXX)."""

from unittest.mock import AsyncMock, patch

import pytest

from services.mesh_brain.community_clusterer import (
    CommunityCluserer,
    cluster_graph,
)


def _make_edges(pairs: list[tuple[str, str, float]]) -> list[dict]:
    return [
        {"from_node": a, "to_node": b, "weight": w, "id": f"{a}-{b}", "edge_type": "co_access", "origin": "extracted"}
        for a, b, w in pairs
    ]


# ---------------------------------------------------------------------------
# cluster_graph (pure function)
# ---------------------------------------------------------------------------

def test_cluster_graph_empty_returns_empty():
    result = cluster_graph([])
    assert result == []


def test_cluster_graph_single_edge_returns_one_centroid():
    edges = _make_edges([("n1", "n2", 1.0)])
    centroids = cluster_graph(edges)
    assert len(centroids) == 1
    assert centroids[0] in ("n1", "n2")


def test_cluster_graph_triangle_returns_one_centroid():
    """Three fully-connected nodes → one community → one centroid."""
    edges = _make_edges([("n1", "n2", 1.0), ("n2", "n3", 1.0), ("n1", "n3", 1.0)])
    centroids = cluster_graph(edges)
    assert len(centroids) == 1


def test_cluster_graph_two_components_returns_two_centroids():
    """Two disconnected triangles → two communities → two centroids."""
    edges = _make_edges([
        ("a1", "a2", 1.0), ("a2", "a3", 1.0), ("a1", "a3", 1.0),
        ("b1", "b2", 1.0), ("b2", "b3", 1.0), ("b1", "b3", 1.0),
    ])
    centroids = cluster_graph(edges)
    assert len(centroids) == 2
    assert set(centroids).issubset({"a1", "a2", "a3", "b1", "b2", "b3"})


# ---------------------------------------------------------------------------
# CommunityCluserer (async, uses MeshDB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_seeds_anchors_from_centroids():
    """run() fetches edges, clusters, and promotes centroid nodes to anchors."""
    db = AsyncMock()
    db.fetch_edges = AsyncMock(return_value=_make_edges([
        ("n1", "n2", 1.0), ("n2", "n3", 1.0), ("n1", "n3", 1.0),
    ]))
    db.promote_to_anchor = AsyncMock()

    clusterer = CommunityCluserer(db)
    promoted = await clusterer.run()

    assert len(promoted) == 1
    db.promote_to_anchor.assert_called_once_with(promoted[0])


@pytest.mark.asyncio
async def test_run_empty_graph_promotes_nothing():
    db = AsyncMock()
    db.fetch_edges = AsyncMock(return_value=[])
    db.promote_to_anchor = AsyncMock()

    clusterer = CommunityCluserer(db)
    promoted = await clusterer.run()

    assert promoted == []
    db.promote_to_anchor.assert_not_called()
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

```bash
cd autobot-backend
python -m pytest services/mesh_brain/community_clusterer_test.py -v
```

Expected: `ERROR — ModuleNotFoundError: No module named 'services.mesh_brain.community_clusterer'`

- [ ] **Step 3: Create `community_clusterer.py`**

Create `autobot-backend/services/mesh_brain/community_clusterer.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Leiden community clustering for anchor seeding in NeuralMeshRetriever (#XXXX).

Builds a NetworkX graph from MeshDB edges, runs Leiden community detection,
selects the highest-degree node in each community as centroid, and promotes
those centroids to anchor nodes via MeshDB.promote_to_anchor().

graspologic is lazy-imported to avoid numba JIT startup overhead (~3s) on
every process start. The import only occurs when cluster_graph() is called.
"""

import logging
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)

_MAX_COMMUNITY_FRACTION = 0.25
_MIN_SPLIT_SIZE = 10


def cluster_graph(edges: list[dict]) -> list[str]:
    """Build undirected graph from edge dicts and return centroid node IDs.

    Args:
        edges: List of dicts with keys 'from_node', 'to_node', 'weight'.

    Returns:
        List of node ID strings — one centroid per detected community.
        Empty list when edges is empty or all nodes are isolated.
    """
    if not edges:
        return []

    # Lazy import — avoids ~3s numba JIT on cold start.
    try:
        from graspologic.partition import leiden
    except ImportError as exc:
        logger.error("graspologic not installed — cannot run Leiden: %s", exc)
        return []

    G = nx.Graph()
    for e in edges:
        G.add_edge(e["from_node"], e["to_node"], weight=float(e["weight"]))

    if G.number_of_nodes() == 0:
        return []

    try:
        partition: dict[Any, int] = leiden(G, trials=3)
    except Exception:
        logger.exception("Leiden failed — falling back to empty partition")
        return []

    # Group nodes by community.
    communities: dict[int, list[str]] = {}
    for node, comm_id in partition.items():
        communities.setdefault(comm_id, []).append(str(node))

    total_nodes = G.number_of_nodes()
    centroids: list[str] = []

    for comm_id, comm_nodes in communities.items():
        # Split oversized communities (>25 % of graph or >=10 members).
        if (
            len(comm_nodes) / total_nodes > _MAX_COMMUNITY_FRACTION
            and len(comm_nodes) >= _MIN_SPLIT_SIZE
        ):
            sub_centroids = _split_community(G.subgraph(comm_nodes))
            centroids.extend(sub_centroids)
        else:
            centroid = _pick_centroid(G.subgraph(comm_nodes), comm_nodes)
            centroids.append(centroid)

    logger.info(
        "cluster_graph: %d nodes, %d edges → %d communities, %d centroids",
        G.number_of_nodes(),
        G.number_of_edges(),
        len(communities),
        len(centroids),
    )
    return centroids


def _pick_centroid(subgraph: nx.Graph, nodes: list[str]) -> str:
    """Return the highest-degree node in nodes within subgraph."""
    return max(nodes, key=lambda n: subgraph.degree(n))


def _split_community(subgraph: nx.Graph) -> list[str]:
    """Apply a second Leiden pass to an oversized community subgraph.

    Returns one centroid per sub-community, or a single centroid if the
    re-partition fails or produces only one group.
    """
    if subgraph.number_of_nodes() < 2:
        return list(subgraph.nodes)[:1]

    try:
        from graspologic.partition import leiden

        sub_partition = leiden(subgraph, trials=2)
    except Exception:
        logger.warning("_split_community Leiden failed; using single centroid")
        nodes = list(subgraph.nodes)
        return [_pick_centroid(subgraph, nodes)]

    sub_communities: dict[int, list[str]] = {}
    for node, comm_id in sub_partition.items():
        sub_communities.setdefault(comm_id, []).append(str(node))

    if len(sub_communities) <= 1:
        nodes = list(subgraph.nodes)
        return [_pick_centroid(subgraph, nodes)]

    return [
        _pick_centroid(subgraph.subgraph(sub_nodes), sub_nodes)
        for sub_nodes in sub_communities.values()
    ]


class CommunityCluserer:
    """Async service: fetch mesh edges, cluster, promote centroids to anchors.

    Usage:
        clusterer = CommunityCluserer(mesh_db)
        promoted_ids = await clusterer.run()
    """

    def __init__(self, db: Any) -> None:
        """
        Args:
            db: MeshDB instance (must have fetch_edges() and promote_to_anchor()).
        """
        self._db = db

    async def run(self, min_weight: float = 0.3) -> list[str]:
        """Fetch edges, cluster, promote centroids, return promoted node IDs.

        Args:
            min_weight: Only edges at or above this weight are included.

        Returns:
            List of node IDs promoted to anchor status.
        """
        edges = await self._db.fetch_edges(min_weight=min_weight)
        if not edges:
            logger.info("CommunityCluserer.run: no edges above weight=%.2f", min_weight)
            return []

        centroids = cluster_graph(edges)
        if not centroids:
            return []

        for node_id in centroids:
            await self._db.promote_to_anchor(node_id)

        logger.info("CommunityCluserer.run: promoted %d anchor nodes", len(centroids))
        return centroids
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest services/mesh_brain/community_clusterer_test.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add services/mesh_brain/community_clusterer.py services/mesh_brain/community_clusterer_test.py
git commit -m "feat(mesh): add CommunityCluserer with Leiden anchor seeding (#XXXX)"
```

---

## Task C: AST Code Indexer (tree-sitter)

**Files:**
- Create: `autobot-backend/services/knowledge/code_indexer.py`
- Create: `autobot-backend/services/knowledge/code_indexer_test.py`

### C1 — Tests first

- [ ] **Step 1: Create the test file**

Create `autobot-backend/services/knowledge/code_indexer_test.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for CodeIndexer (#XXXX)."""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.knowledge.code_indexer import (
    CodeIndexer,
    _make_node_id,
    extract_python,
)

# ---------------------------------------------------------------------------
# Pure extraction helpers
# ---------------------------------------------------------------------------

SIMPLE_PYTHON = b"""
def greet(name: str) -> str:
    return "hello " + name

class Greeter:
    def run(self) -> None:
        greet("world")
"""


def test_make_node_id_is_stable_and_lowercase():
    nid = _make_node_id("MyFunc", "src/auth.py")
    assert nid == "auth::myfunc"
    assert nid == _make_node_id("MyFunc", "src/auth.py")


def test_extract_python_finds_function_nodes():
    result = extract_python("module.py", SIMPLE_PYTHON)
    node_names = [n["name"] for n in result["nodes"]]
    assert "greet" in node_names


def test_extract_python_finds_class_nodes():
    result = extract_python("module.py", SIMPLE_PYTHON)
    node_names = [n["name"] for n in result["nodes"]]
    assert "Greeter" in node_names


def test_extract_python_finds_call_edge():
    result = extract_python("module.py", SIMPLE_PYTHON)
    edge_pairs = [(e["source"], e["target_name"]) for e in result["edges"]]
    assert any(target == "greet" for _, target in edge_pairs)


def test_extract_python_no_duplicate_edges():
    result = extract_python("module.py", SIMPLE_PYTHON)
    pairs = [(e["source"], e["target_name"]) for e in result["edges"]]
    assert len(pairs) == len(set(pairs))


# ---------------------------------------------------------------------------
# CodeIndexer (uses ChromaDB + embed model mocks)
# ---------------------------------------------------------------------------

def _make_indexer(tmp_path: Path):
    collection = MagicMock()
    collection.upsert = MagicMock()
    embed_model = MagicMock()
    embed_model.get_text_embedding = MagicMock(return_value=[0.1] * 384)
    cache_file = tmp_path / ".code_index_hashes.json"
    return CodeIndexer(collection=collection, embed_model=embed_model, cache_file=cache_file)


def test_index_python_file_upserts_nodes(tmp_path):
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)

    indexer = _make_indexer(tmp_path)
    result = indexer.index_file(str(src), root_dir=str(tmp_path))

    assert result.success > 0
    assert indexer._collection.upsert.called


def test_index_unchanged_file_skips(tmp_path):
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)

    indexer = _make_indexer(tmp_path)
    indexer.index_file(str(src), root_dir=str(tmp_path))
    call_count_first = indexer._collection.upsert.call_count

    # Second call — hash unchanged
    result = indexer.index_file(str(src), root_dir=str(tmp_path))

    assert result.skipped == 1
    assert indexer._collection.upsert.call_count == call_count_first


def test_force_reindex_bypasses_cache(tmp_path):
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)

    indexer = _make_indexer(tmp_path)
    indexer.index_file(str(src), root_dir=str(tmp_path))
    call_count_first = indexer._collection.upsert.call_count

    result = indexer.index_file(str(src), root_dir=str(tmp_path), force=True)

    assert result.success > 0
    assert indexer._collection.upsert.call_count > call_count_first
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

```bash
cd autobot-backend
python -m pytest services/knowledge/code_indexer_test.py -v
```

Expected: `ERROR — ModuleNotFoundError: No module named 'services.knowledge.code_indexer'`

- [ ] **Step 3: Create `code_indexer.py`**

Create `autobot-backend/services/knowledge/code_indexer.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AST-based code indexer using tree-sitter (#XXXX).

Two-pass extraction per source file:
  Pass 1 (structural): walk AST for function/class/import declarations → nodes.
  Pass 2 (call-graph): walk function bodies for call expressions → edges.

Results are embedded and upserted into ChromaDB following the same
SHA-256 content-hash cache + _embed_and_upsert pattern as DocIndexer.

Supported languages: Python, JavaScript/TypeScript.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass (mirrors DocIndexer.IndexResult)
# ---------------------------------------------------------------------------


@dataclass
class CodeIndexResult:
    success: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stable node ID
# ---------------------------------------------------------------------------


def _make_node_id(name: str, source_path: str) -> str:
    """Stable, lowercase ID: '<stem>::<safe_name>'.

    Strips special characters so IDs survive renames of individual symbols.
    """
    stem = Path(source_path).stem
    safe = re.sub(r"[^a-z0-9_]", "", name.lower().replace(".", "_"))
    return f"{stem}::{safe}"


# ---------------------------------------------------------------------------
# Python extractor
# ---------------------------------------------------------------------------


def extract_python(source_path: str, content: bytes) -> dict:
    """Two-pass tree-sitter extraction for Python.

    Returns:
        {
            "nodes": [{"id": str, "name": str, "kind": str, "source_path": str, "line": int}],
            "edges": [{"source": str, "target_name": str, "kind": "calls", "source_path": str}],
        }
    """
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
    except ImportError as exc:
        logger.error("tree-sitter-python not installed: %s", exc)
        return {"nodes": [], "edges": []}

    lang = Language(tspython.language())
    parser = Parser(lang)
    tree = parser.parse(content)

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()

    # ---- Pass 1: structural declarations ----
    _py_structural(tree.root_node, source_path, nodes, parent_scope=None)

    # ---- Pass 2: call graph ----
    _py_call_graph(tree.root_node, source_path, nodes, edges, seen_edges, current_scope=None)

    return {"nodes": list(nodes.values()), "edges": edges}


def _py_structural(node: Any, source_path: str, nodes: dict, parent_scope: Optional[str]) -> None:
    """Recurse AST collecting function_definition and class_definition nodes."""
    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        if name_node:
            name = name_node.text.decode("utf-8")
            nid = _make_node_id(name, source_path)
            nodes[nid] = {
                "id": nid,
                "name": name,
                "kind": "function",
                "source_path": source_path,
                "line": node.start_point[0] + 1,
                "parent": parent_scope,
            }
            for child in node.children:
                _py_structural(child, source_path, nodes, parent_scope=nid)
            return

    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        if name_node:
            name = name_node.text.decode("utf-8")
            nid = _make_node_id(name, source_path)
            nodes[nid] = {
                "id": nid,
                "name": name,
                "kind": "class",
                "source_path": source_path,
                "line": node.start_point[0] + 1,
                "parent": parent_scope,
            }
            for child in node.children:
                _py_structural(child, source_path, nodes, parent_scope=nid)
            return

    for child in node.children:
        _py_structural(child, source_path, nodes, parent_scope)


def _py_call_graph(
    node: Any,
    source_path: str,
    nodes: dict,
    edges: list,
    seen: set,
    current_scope: Optional[str],
) -> None:
    """Recurse AST collecting call_expression targets within function bodies."""
    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        scope = _make_node_id(name_node.text.decode("utf-8"), source_path) if name_node else current_scope
        for child in node.children:
            _py_call_graph(child, source_path, nodes, edges, seen, scope)
        return

    if node.type == "call" and current_scope:
        func_node = node.child_by_field_name("function")
        if func_node:
            raw = func_node.text.decode("utf-8").split("(")[0]
            target_name = raw.split(".")[-1]  # strip object prefix
            pair = (current_scope, target_name)
            if pair not in seen:
                seen.add(pair)
                edges.append({
                    "source": current_scope,
                    "target_name": target_name,
                    "kind": "calls",
                    "source_path": source_path,
                    "origin": "extracted",
                })

    for child in node.children:
        _py_call_graph(child, source_path, nodes, edges, seen, current_scope)


# ---------------------------------------------------------------------------
# Language dispatch
# ---------------------------------------------------------------------------

_EXTRACTORS = {
    ".py": extract_python,
}

try:
    import tree_sitter_javascript as tsjs
    from tree_sitter import Language, Parser as _Parser

    def extract_javascript(source_path: str, content: bytes) -> dict:
        """Two-pass extraction for JavaScript/TypeScript (structural + calls)."""
        lang = Language(tsjs.language())
        parser = _Parser(lang)
        tree = parser.parse(content)

        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        seen_edges: set[tuple[str, str]] = set()

        _js_structural(tree.root_node, source_path, nodes, parent_scope=None)
        _js_call_graph(tree.root_node, source_path, nodes, edges, seen_edges, current_scope=None)

        return {"nodes": list(nodes.values()), "edges": edges}

    def _js_structural(node: Any, source_path: str, nodes: dict, parent_scope: Optional[str]) -> None:
        if node.type in ("function_declaration", "arrow_function", "function_expression"):
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else f"anon_{node.start_point[0]}"
            nid = _make_node_id(name, source_path)
            nodes[nid] = {
                "id": nid,
                "name": name,
                "kind": "function",
                "source_path": source_path,
                "line": node.start_point[0] + 1,
                "parent": parent_scope,
            }
            for child in node.children:
                _js_structural(child, source_path, nodes, parent_scope=nid)
            return
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode("utf-8")
                nid = _make_node_id(name, source_path)
                nodes[nid] = {
                    "id": nid,
                    "name": name,
                    "kind": "class",
                    "source_path": source_path,
                    "line": node.start_point[0] + 1,
                    "parent": parent_scope,
                }
        for child in node.children:
            _js_structural(child, source_path, nodes, parent_scope)

    def _js_call_graph(
        node: Any,
        source_path: str,
        nodes: dict,
        edges: list,
        seen: set,
        current_scope: Optional[str],
    ) -> None:
        if node.type in ("function_declaration", "arrow_function", "function_expression"):
            name_node = node.child_by_field_name("name")
            scope = _make_node_id(name_node.text.decode("utf-8"), source_path) if name_node else current_scope
            for child in node.children:
                _js_call_graph(child, source_path, nodes, edges, seen, scope)
            return
        if node.type == "call_expression" and current_scope:
            func_node = node.child_by_field_name("function")
            if func_node:
                raw = func_node.text.decode("utf-8").split("(")[0]
                target_name = raw.split(".")[-1]
                pair = (current_scope, target_name)
                if pair not in seen:
                    seen.add(pair)
                    edges.append({
                        "source": current_scope,
                        "target_name": target_name,
                        "kind": "calls",
                        "source_path": source_path,
                        "origin": "extracted",
                    })
        for child in node.children:
            _js_call_graph(child, source_path, nodes, edges, seen, current_scope)

    for ext in (".js", ".ts", ".jsx", ".tsx", ".vue"):
        _EXTRACTORS[ext] = extract_javascript

except ImportError:
    logger.info("tree-sitter-javascript not installed; JS/TS indexing disabled")


# ---------------------------------------------------------------------------
# CodeIndexer
# ---------------------------------------------------------------------------

_DEFAULT_CACHE = Path(".code_index_hashes.json")


class CodeIndexer:
    """Index source files into ChromaDB using AST extraction.

    Mirrors DocIndexer's SHA-256 hash cache + _embed_and_upsert pattern.
    Each function/class node becomes one ChromaDB document. Call edges are
    stored in node metadata for downstream graph construction.

    Usage:
        indexer = CodeIndexer(collection=chroma_col, embed_model=embed_model)
        result = indexer.index_file("/path/to/module.py", root_dir="/path/to")
    """

    def __init__(
        self,
        collection: Any,
        embed_model: Any,
        cache_file: Path = _DEFAULT_CACHE,
    ) -> None:
        self._collection = collection
        self._embed_model = embed_model
        self._cache_file = cache_file
        self._hash_cache: dict[str, str] = self._load_cache()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_file(
        self,
        file_path: str,
        root_dir: str,
        force: bool = False,
    ) -> CodeIndexResult:
        """Extract AST nodes from file_path and upsert into ChromaDB.

        Args:
            file_path: Absolute path to the source file.
            root_dir:  Repository root — used for relative path keys.
            force:     If True, skip hash cache and always re-index.

        Returns:
            CodeIndexResult with success/failed/skipped counts.
        """
        result = CodeIndexResult()
        ext = Path(file_path).suffix.lower()
        extractor = _EXTRACTORS.get(ext)
        if extractor is None:
            result.skipped += 1
            return result

        # Hash check
        rel_path = str(Path(file_path).relative_to(root_dir))
        if not force:
            current_hash = self._compute_hash(file_path)
            if current_hash and self._hash_cache.get(rel_path) == current_hash:
                result.skipped += 1
                return result

        try:
            content = Path(file_path).read_bytes()
        except OSError as e:
            result.failed += 1
            result.errors.append(str(e))
            return result

        extracted = extractor(file_path, content)
        nodes = extracted["nodes"]
        edges = extracted["edges"]

        # Build call edge index by source node for metadata
        calls_by_source: dict[str, list[str]] = {}
        for e in edges:
            calls_by_source.setdefault(e["source"], []).append(e["target_name"])

        for node in nodes:
            ok = self._upsert_node(node, rel_path, calls_by_source)
            if ok:
                result.success += 1
            else:
                result.failed += 1

        # Update cache
        new_hash = self._compute_hash(file_path)
        if new_hash:
            self._hash_cache[rel_path] = new_hash
            self._save_cache()

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _upsert_node(
        self,
        node: dict,
        rel_path: str,
        calls_by_source: dict[str, list[str]],
    ) -> bool:
        """Embed node content and upsert into ChromaDB. Returns True on success."""
        content = (
            f"{node['kind'].upper()} {node['name']}\n"
            f"File: {rel_path} line {node.get('line', 0)}"
        )
        metadata: dict[str, Any] = {
            "source": "autobot_code",
            "node_kind": node["kind"],
            "node_name": node["name"],
            "source_path": rel_path,
            "line": str(node.get("line", 0)),
            "parent": node.get("parent") or "",
            "calls": ",".join(calls_by_source.get(node["id"], [])),
            "origin": "extracted",
        }
        try:
            embedding = self._embed_model.get_text_embedding(content)
            self._collection.upsert(
                ids=[node["id"]],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata],
            )
            return True
        except Exception as e:
            logger.error("Failed to upsert node %s: %s", node["id"], e)
            return False

    @staticmethod
    def _compute_hash(file_path: str) -> str:
        try:
            return hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
        except OSError:
            return ""

    def _load_cache(self) -> dict[str, str]:
        if self._cache_file.exists():
            try:
                return json.loads(self._cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_cache(self) -> None:
        try:
            self._cache_file.write_text(
                json.dumps(self._hash_cache, indent=2), encoding="utf-8"
            )
        except OSError as e:
            logger.warning("Could not save code index cache: %s", e)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest services/knowledge/code_indexer_test.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Run full knowledge test suite — no regressions**

```bash
python -m pytest services/knowledge/ -v
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add services/knowledge/code_indexer.py services/knowledge/code_indexer_test.py
git commit -m "feat(knowledge): add tree-sitter AST code indexer with SHA-256 cache (#XXXX)"
```

---

## Final: Verify All Tests Pass + Push

- [ ] **Step 1: Full test run**

```bash
cd autobot-backend
python -m pytest services/graph_rag_service_test.py services/mesh_brain/community_clusterer_test.py services/mesh_brain/mesh_db_test.py services/mesh_brain/mesh_db_adapter_test.py services/knowledge/code_indexer_test.py -v
```

Expected: all pass.

- [ ] **Step 2: Import smoke-check**

```bash
python -c "from services.graph_rag_service import GraphRAGService; print('ok')"
python -c "from services.mesh_brain.community_clusterer import CommunityCluserer; print('ok')"
python -c "from services.knowledge.code_indexer import CodeIndexer; print('ok')"
python -c "from services.mesh_brain.mesh_db import MeshDB; print('ok')"
```

Expected: each prints `ok`.

- [ ] **Step 3: Push and create PRs**

```bash
git push -u origin issue-XXXX
gh pr create --title "feat: graphify gaps — EdgeOrigin taxonomy, Leiden anchors, AST code indexer" \
  --body "Closes #XXXX, #XXXX, #XXXX

## Changes
- **EdgeOrigin taxonomy**: \`source_provenance\` field (extracted/inferred/ambiguous) propagated in GraphRAGService relation metadata
- **Leiden anchor seeding**: \`CommunityCluserer\` service clusters mesh graph and promotes centroids; \`MeshDB.get_anchor_neighbors()\` satisfies \`_AnchorDB\` Protocol
- **AST code indexer**: \`CodeIndexer\` uses tree-sitter two-pass extraction (structural + call-graph) for Python and JS/TS; SHA-256 cache + ChromaDB upsert mirrors DocIndexer pattern

## Test plan
- [ ] All new tests pass (\`pytest\` output attached)
- [ ] No regressions in existing test suites
- [ ] Import smoke-check passes for all 4 modified/created modules" \
  --base Dev_new_gui
```
