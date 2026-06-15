# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Project timeline / Gantt helpers (GH#9020).

Pure functions for the project timeline view: computing the critical path
through a dependency DAG of work items. Kept free of ORM/IO so it can be unit
tested directly.
"""

from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

# (predecessor_id, successor_id) — predecessor must finish before successor starts.
Edge = Tuple[str, str]

# Default span (days) for an item that has no/invalid scheduled dates, so it
# still participates in the critical-path length with a non-zero weight.
DEFAULT_DURATION_DAYS = 1.0


def duration_days(start: Optional[datetime], end: Optional[datetime]) -> float:
    """Planned duration in days, or ``DEFAULT_DURATION_DAYS`` when unschedulable."""
    if start and end and end > start:
        return (end - start).total_seconds() / 86400.0
    return DEFAULT_DURATION_DAYS


def _topological_order(nodes: Set[str], succ: Dict[str, List[str]]) -> List[str]:
    """Kahn topological sort. Nodes still incoming after draining (i.e. inside a
    cycle) are appended in arbitrary order so the caller degrades gracefully
    rather than dropping them."""
    indegree: Dict[str, int] = {n: 0 for n in nodes}
    for src in succ:
        for dst in succ[src]:
            indegree[dst] += 1

    queue = deque(sorted(n for n in nodes if indegree[n] == 0))
    order: List[str] = []
    while queue:
        n = queue.popleft()
        order.append(n)
        for dst in succ.get(n, []):
            indegree[dst] -= 1
            if indegree[dst] == 0:
                queue.append(dst)

    if len(order) < len(nodes):  # cycle — keep remaining nodes, edges into them ignored
        order.extend(sorted(nodes - set(order)))
    return order


def compute_critical_path(durations: Dict[str, float], edges: List[Edge]) -> Set[str]:
    """Return the set of node ids on the critical (longest-duration) path.

    ``durations`` maps node id → duration (any positive unit). ``edges`` are
    (predecessor, successor) pairs. Edges referencing unknown nodes are ignored.
    Cycles are tolerated (offending edges are skipped via the topo fallback).
    Returns an empty set when there are no nodes.
    """
    nodes = set(durations)
    if not nodes:
        return set()

    succ: Dict[str, List[str]] = {n: [] for n in nodes}
    for pred, nxt in edges:
        if pred in nodes and nxt in nodes and pred != nxt:
            succ[pred].append(nxt)

    order = _topological_order(nodes, succ)
    seen: Set[str] = set()
    # Longest finish-time to each node + the predecessor that achieved it.
    dist: Dict[str, float] = {}
    best_pred: Dict[str, str] = {}
    for n in order:
        dist[n] = durations.get(n, 0.0)
        seen.add(n)
        # best incoming predecessor already finalized in topo order
        incoming = [p for p in nodes if n in succ.get(p, []) and p in seen and p != n]
        if incoming:
            top = max(incoming, key=lambda p: dist[p])
            dist[n] = dist[top] + durations.get(n, 0.0)
            best_pred[n] = top

    end = max(dist, key=lambda n: dist[n])
    path: Set[str] = set()
    cur = end
    while cur is not None:
        path.add(cur)
        cur = best_pred.get(cur)
    return path
