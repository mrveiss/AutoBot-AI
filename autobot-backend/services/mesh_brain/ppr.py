# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Personalized PageRank over the mesh graph for importance-weighted expansion (#1994, #2057)."""

from typing import Protocol

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


# =============================================================================
# Protocol
# =============================================================================


class MeshDB(Protocol):
    """Protocol for mesh database neighbor lookups used by PPR."""

    async def get_neighbors(self, node_id: str, min_weight: float) -> list[dict]:
        """Return list of {"to_node": str, "weight": float} for node_id."""
        ...


# =============================================================================
# Subgraph
# =============================================================================


class Subgraph:
    """Lightweight in-memory directed graph for PPR computation."""

    def __init__(self, nodes: set, edges: list[tuple[str, str, float]]) -> None:
        self.nodes = nodes
        self._in_edges: dict[str, list[tuple[str, float]]] = {}
        self._out_degree: dict[str, int] = {}
        for src, tgt, weight in edges:
            self._in_edges.setdefault(tgt, []).append((src, weight))
            self._out_degree[src] = self._out_degree.get(src, 0) + 1

    def in_edges(self, node: str) -> list[tuple[str, float]]:
        """Return [(source_node, weight), ...] for all edges into node."""
        return self._in_edges.get(node, [])

    def out_degree(self, node: str) -> int:
        """Return the number of outgoing edges from node."""
        return self._out_degree.get(node, 0)


# =============================================================================
# PersonalizedPageRank
# =============================================================================


class PersonalizedPageRank:
    """PPR over the mesh graph for importance-weighted expansion.

    Replaces BFS for knowledge retrieval graph expansion. Edge weights
    directly influence propagation — high-weight edges (reinforced by
    EdgeLearner) propagate more relevance.
    """

    def __init__(self, db: MeshDB) -> None:
        """
        Args:
            db: MeshDB instance for subgraph loading (get_neighbors).
        """
        self.db = db

    async def rank(
        self,
        seed_node_ids: list[str],
        alpha: float = 0.15,
        max_iterations: int = 20,
        min_weight: float = 0.3,
        top_k: int = 20,
    ) -> list[tuple[str, float]]:
        """Run PPR from seed nodes. Returns [(node_id, ppr_score), ...] sorted desc."""
        subgraph = await self._load_subgraph(seed_node_ids, max_hops=3, min_weight=min_weight)
        if not subgraph.nodes:
            return self._uniform_seed_scores(seed_node_ids)
        scores = self._init_scores(seed_node_ids, subgraph.nodes)
        scores = self._power_iterate(scores, subgraph, seed_node_ids, alpha, max_iterations)
        return sorted(scores.items(), key=lambda x: -x[1])[:top_k]

    # ------------------------------------------------------------------
    # Private helpers — each kept under 30 lines
    # ------------------------------------------------------------------

    def _uniform_seed_scores(self, seed_node_ids: list[str]) -> list[tuple[str, float]]:
        """Return uniform 1/n scores for each seed when subgraph is empty."""
        uniform = 1.0 / len(seed_node_ids)
        return [(nid, uniform) for nid in seed_node_ids]

    def _init_scores(self, seed_node_ids: list[str], all_nodes: set) -> dict[str, float]:
        """Initialise PPR score vector: 1/n for seeds, 0 for others."""
        n_seeds = len(seed_node_ids)
        seed_set = set(seed_node_ids)
        return {nid: (1.0 / n_seeds if nid in seed_set else 0.0) for nid in all_nodes}

    def _power_iterate(
        self,
        scores: dict[str, float],
        subgraph: Subgraph,
        seed_node_ids: list[str],
        alpha: float,
        max_iterations: int,
    ) -> dict[str, float]:
        """Run power iterations until convergence or max_iterations reached."""
        n_seeds = len(seed_node_ids)
        seed_set = set(seed_node_ids)
        for _ in range(max_iterations):
            new_scores = self._single_iteration(scores, subgraph, seed_set, n_seeds, alpha)
            if self._converged(scores, new_scores):
                return new_scores
            scores = new_scores
        return scores

    def _single_iteration(
        self,
        scores: dict[str, float],
        subgraph: Subgraph,
        seed_set: set,
        n_seeds: int,
        alpha: float,
    ) -> dict[str, float]:
        """Compute one PPR power-iteration step and return new score vector."""
        new_scores: dict[str, float] = {}
        for node in subgraph.nodes:
            teleport = alpha * (1.0 / n_seeds if node in seed_set else 0.0)
            propagation = self._propagation_sum(node, scores, subgraph)
            new_scores[node] = teleport + (1 - alpha) * propagation
        return new_scores

    def _propagation_sum(self, node: str, scores: dict[str, float], subgraph: Subgraph) -> float:
        """Sum weighted contributions from in-edge neighbors for one node."""
        total = 0.0
        for neighbor, edge_weight in subgraph.in_edges(node):
            out_deg = subgraph.out_degree(neighbor)
            if out_deg > 0:
                total += scores.get(neighbor, 0.0) * edge_weight / out_deg
        return total

    async def _load_subgraph(self, seed_ids: list[str], max_hops: int, min_weight: float) -> Subgraph:
        """BFS from seed_ids up to max_hops; returns Subgraph of collected nodes/edges."""
        visited: set[str] = set(seed_ids)
        frontier: list[str] = list(seed_ids)
        edges: list[tuple[str, str, float]] = []

        for _ in range(max_hops):
            frontier, new_edges = await self._expand_frontier(frontier, visited, min_weight)
            edges.extend(new_edges)
            if not frontier:
                break

        return Subgraph(visited, edges)

    async def _expand_frontier(
        self, frontier: list[str], visited: set[str], min_weight: float
    ) -> tuple[list[str], list[tuple[str, str, float]]]:
        """Expand one BFS hop. Returns (next_frontier, new_edges)."""
        next_frontier: list[str] = []
        new_edges: list[tuple[str, str, float]] = []
        for node_id in frontier:
            neighbors = await self.db.get_neighbors(node_id, min_weight=min_weight)
            for neighbor in neighbors:
                nid = neighbor["to_node"]
                new_edges.append((node_id, nid, neighbor["weight"]))
                if nid not in visited:
                    visited.add(nid)
                    next_frontier.append(nid)
        return next_frontier, new_edges

    @staticmethod
    def _converged(old: dict[str, float], new: dict[str, float], tol: float = 1e-6) -> bool:
        """Return True when L1 distance between score vectors is below tol."""
        return sum(abs(old.get(k, 0.0) - new.get(k, 0.0)) for k in new) < tol
