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
    return {node: comm_id for comm_id, nodes in enumerate(communities) for node in nodes}


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

    G = nx.Graph()
    for e in edges:
        G.add_edge(e["from_node"], e["to_node"], weight=float(e["weight"]))

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
