# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Community clustering for anchor seeding in NeuralMeshRetriever (#4819).

Builds a NetworkX graph from MeshDB edges, runs Louvain community detection,
selects the highest-degree node in each community as centroid, and promotes
those centroids to anchor nodes via MeshDB.promote_to_anchor().

Uses NetworkX's built-in Louvain (weight-aware, deterministic via seed). This
replaces graspologic Leiden, which pinned numpy<2.0 and could not install on
Python 3.13+ (#10524). NetworkX is lazy-imported in the helpers below so module
import stays cheap when clustering is unused.
"""

from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_MAX_COMMUNITY_FRACTION = 0.25
_MIN_SPLIT_SIZE = 10
# Fixed seed → deterministic community detection across runs (Louvain is randomized).
_LOUVAIN_SEED = 42


def _detect_communities(graph: Any) -> dict[Any, int]:
    """Partition graph into communities, returning {node: community_id}.

    Weight-aware Louvain via NetworkX — numpy-2 / py3.13 compatible. Replaces the
    graspologic Leiden call (same return contract) without adding a dependency.
    """
    from networkx.algorithms.community import louvain_communities

    communities = louvain_communities(graph, weight="weight", seed=_LOUVAIN_SEED)
    # #13473: ids follow (-size, sorted members), never the partitioner's
    # enumeration order, so an unchanged grouping keeps its id.
    ordered = sorted(communities, key=lambda nodes: (-len(nodes), tuple(sorted(map(str, nodes)))))
    # `louvain_communities` hands back *sets*, so iterating one directly would
    # seed this dict in hash order and every list built from it downstream would
    # vary per process. Ordering the members as well as the communities is what
    # makes the whole return value reproducible, not just the ids.
    return {node: comm_id for comm_id, nodes in enumerate(ordered) for node in sorted(nodes, key=str)}


def _edge_order(edge: dict) -> tuple:
    """A total order over edges that ignores which endpoint is listed first.

    Within one node pair, higher weights sort first, so the last one added -- the
    weight that is kept -- is the lowest, as under fetch_edges' ``weight DESC``.
    """
    a, b = str(edge["from_node"]), str(edge["to_node"])
    return (min(a, b), max(a, b), -float(edge["weight"]), a, b)


def _build_graph(edges: list[dict]) -> Any:
    """Build the undirected graph in an order that depends only on its content.

    #13473: Louvain is seeded, but it visits nodes in adjacency order, so the same
    edges inserted in a different order give a different *membership*, not just
    different ids. fetch_edges orders by weight alone, and PostgreSQL returns
    equal weights in no guaranteed order, so an unchanged mesh arrived in a new
    order on each run. Sorting nodes and edges first removes that input.
    """
    import networkx as nx  # lazy import — avoids startup cost when clustering unused

    graph = nx.Graph()
    graph.add_nodes_from(sorted({e[k] for e in edges for k in ("from_node", "to_node")}, key=str))
    for e in sorted(edges, key=_edge_order):
        graph.add_edge(e["from_node"], e["to_node"], weight=float(e["weight"]))
    return graph


def cluster_graph(edges: list[dict]) -> list[str]:
    """Build undirected graph from edge dicts and return centroid node IDs.

    Args:
        edges: List of dicts with keys 'from_node', 'to_node', 'weight'.

    Returns:
        One centroid node ID per detected community. Empty list when edges is empty.
    """
    if not edges:
        return []

    G = _build_graph(edges)

    if G.number_of_nodes() == 0:
        return []

    try:
        partition: dict[Any, int] = _detect_communities(G)
    except Exception:
        logger.exception("Community detection failed — falling back to empty partition")
        return []

    communities: dict[int, list[str]] = {}
    for node, comm_id in partition.items():
        communities.setdefault(comm_id, []).append(str(node))

    total_nodes = G.number_of_nodes()
    centroids: list[str] = []

    for comm_id in sorted(communities):
        comm_nodes = communities[comm_id]
        if len(comm_nodes) / total_nodes > _MAX_COMMUNITY_FRACTION and len(comm_nodes) >= _MIN_SPLIT_SIZE:
            centroids.extend(_split_community(G.subgraph(comm_nodes)))
        else:
            centroids.append(_pick_centroid(G.subgraph(comm_nodes), comm_nodes))

    logger.info(
        "cluster_graph: %d nodes, %d edges → %d communities, %d centroids",
        G.number_of_nodes(),
        G.number_of_edges(),
        len(communities),
        len(centroids),
    )
    return centroids


def _pick_centroid(subgraph, nodes: list[str]) -> str:
    """The highest-degree node in *nodes*, ties broken by name.

    #13473: `max(nodes, key=degree)` returns the *first* maximal element, so on a
    degree tie the answer was whatever order `nodes` happened to arrive in. Ties
    are the common case rather than an edge case -- every node of a triangle has
    degree 2 -- so the anchors promoted for an unchanged mesh differed between
    processes even after community ids were made stable. Ordering the members
    upstream fixes the observed symptom; a total order here is what makes it a
    property of the function instead of a property of its caller.
    """
    return min(nodes, key=lambda n: (-subgraph.degree(n), str(n)))


def _split_community(subgraph) -> list[str]:
    """Apply a second Leiden pass to an oversized community subgraph."""
    if subgraph.number_of_nodes() < 2:
        return list(subgraph.nodes)[:1]

    try:
        sub_partition = _detect_communities(subgraph)
    except Exception:
        logger.warning("_split_community detection failed; using single centroid")
        nodes = list(subgraph.nodes)
        return [_pick_centroid(subgraph, nodes)]

    sub_communities: dict[int, list[str]] = {}
    for node, comm_id in sub_partition.items():
        sub_communities.setdefault(comm_id, []).append(str(node))

    if len(sub_communities) <= 1:
        nodes = list(subgraph.nodes)
        return [_pick_centroid(subgraph, nodes)]

    return [_pick_centroid(subgraph.subgraph(nodes), nodes) for _, nodes in sorted(sub_communities.items())]


class CommunityClusterer:
    """Fetch mesh edges, cluster via Leiden, promote centroids to anchors.

    Usage:
        clusterer = CommunityClusterer(mesh_db)
        promoted_ids = await clusterer.run()
    """

    def __init__(self, db: Any) -> None:
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
            logger.info("CommunityClusterer.run: no edges above weight=%.2f", min_weight)
            return []

        centroids = cluster_graph(edges)
        if not centroids:
            return []

        for node_id in centroids:
            await self._db.promote_to_anchor(node_id)

        logger.info("CommunityClusterer.run: promoted %d anchor nodes", len(centroids))
        return centroids
