# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one neighbour-lookup contract shared by PPR, staleness propagation and edge sync (#18139)."""

from typing import Protocol

Neighbor = tuple[str, float]


class NeighborStore(Protocol):
    """Directed one-hop neighbour lookup over the mesh graph.

    Every mesh graph backend (PostgreSQL adapter, Redis sorted sets) implements
    exactly this signature and row shape, so PPR and staleness BFS accept any of them.
    """

    async def get_neighbors(self, node_id: str, min_weight: float = 0.0) -> list[Neighbor]:
        """Return ``[(neighbor_id, edge_weight)]`` for edges leaving ``node_id`` with weight >= ``min_weight``."""
        ...


def decode_neighbors(raw: list[tuple[bytes | str, float]]) -> list[Neighbor]:
    """Normalise Redis ``ZRANGEBYSCORE ... WITHSCORES`` rows to ``Neighbor`` tuples."""
    return [(member.decode() if isinstance(member, bytes) else member, float(score)) for member, score in raw]
