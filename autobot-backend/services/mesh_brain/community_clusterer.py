# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Leiden community clustering for anchor seeding in NeuralMeshRetriever (#4819).

Builds a NetworkX graph from MeshDB edges, runs Leiden community detection,
selects the highest-degree node in each community as centroid, and promotes
those centroids to anchor nodes via MeshDB.promote_to_anchor().

graspologic is lazy-imported to avoid numba JIT startup overhead on every
process start. The import only occurs when cluster_graph() is called.
"""

from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_MAX_COMMUNITY_FRACTION = 0.25
_MIN_SPLIT_SIZE = 10


def cluster_graph(edges: list[dict]) -> list[str]:
    """Build undirected graph from edge dicts and return centroid node IDs.

    Args:
        edges: List of dicts with keys 'from_node', 'to_node', 'weight'.

    Returns:
        One centroid node ID per detected community. Empty list when edges is empty.
    """
    if not edges:
        return []

    import networkx as nx  # lazy import — avoids startup cost when clustering unused

    try:
        from graspologic.partition import leiden
    except ImportError:
        raise  # let caller handle missing dependency distinctly from empty-graph result

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

    communities: dict[int, list[str]] = {}
    for node, comm_id in partition.items():
        communities.setdefault(comm_id, []).append(str(node))

    total_nodes = G.number_of_nodes()
    centroids: list[str] = []

    for comm_nodes in communities.values():
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
    """Return the highest-degree node in nodes within subgraph."""
    return max(nodes, key=lambda n: subgraph.degree(n))


def _split_community(subgraph) -> list[str]:
    """Apply a second Leiden pass to an oversized community subgraph."""
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

    return [_pick_centroid(subgraph.subgraph(sub_nodes), sub_nodes) for sub_nodes in sub_communities.values()]


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
