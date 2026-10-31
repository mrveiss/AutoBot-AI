# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for CommunityClusterer (#4819, #4834).

Community detection runs on NetworkX's built-in Louvain (#10524), which is always
installed, so no dependency stubbing is required.
"""

from unittest.mock import AsyncMock

import pytest

from services.mesh_brain.community_clusterer import CommunityClusterer, cluster_graph


def _make_edges(pairs: list[tuple[str, str, float]]) -> list[dict]:
    return [
        {
            "from_node": a,
            "to_node": b,
            "weight": w,
            "id": f"{a}-{b}",
            "edge_type": "co_access",
            "origin": "extracted",
        }
        for a, b, w in pairs
    ]


# ---------------------------------------------------------------------------
# cluster_graph (pure function)
# ---------------------------------------------------------------------------


def test_cluster_graph_empty_returns_empty() -> None:
    assert cluster_graph([]) == []


def test_cluster_graph_single_edge_returns_one_centroid() -> None:
    edges = _make_edges([("n1", "n2", 1.0)])
    centroids = cluster_graph(edges)
    assert len(centroids) == 1
    assert centroids[0] in ("n1", "n2")


def test_cluster_graph_triangle_returns_one_centroid() -> None:
    """Three fully-connected nodes → one community → one centroid."""
    edges = _make_edges([("n1", "n2", 1.0), ("n2", "n3", 1.0), ("n1", "n3", 1.0)])
    centroids = cluster_graph(edges)
    assert len(centroids) == 1


def test_cluster_graph_two_components_returns_two_centroids() -> None:
    """Two disconnected triangles → two communities → two centroids."""
    edges = _make_edges(
        [
            ("a1", "a2", 1.0),
            ("a2", "a3", 1.0),
            ("a1", "a3", 1.0),
            ("b1", "b2", 1.0),
            ("b2", "b3", 1.0),
            ("b1", "b3", 1.0),
        ]
    )
    centroids = cluster_graph(edges)
    assert len(centroids) == 2
    assert set(centroids).issubset({"a1", "a2", "a3", "b1", "b2", "b3"})


# ---------------------------------------------------------------------------
# CommunityClusterer (async, uses MeshDB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_seeds_anchors_from_centroids() -> None:
    """run() fetches edges, clusters, and promotes centroid nodes to anchors."""
    db = AsyncMock()
    db.fetch_edges = AsyncMock(
        return_value=_make_edges(
            [
                ("n1", "n2", 1.0),
                ("n2", "n3", 1.0),
                ("n1", "n3", 1.0),
            ]
        )
    )
    db.promote_to_anchor = AsyncMock()

    clusterer = CommunityClusterer(db)
    promoted = await clusterer.run()

    assert len(promoted) == 1
    db.promote_to_anchor.assert_called_once_with(promoted[0])


@pytest.mark.asyncio
async def test_run_empty_graph_promotes_nothing() -> None:
    db = AsyncMock()
    db.fetch_edges = AsyncMock(return_value=[])
    db.promote_to_anchor = AsyncMock()

    clusterer = CommunityClusterer(db)
    promoted = await clusterer.run()

    assert promoted == []
    db.promote_to_anchor.assert_not_called()


# ---------------------------------------------------------------------------
# Periodic scheduler integration (#4834)
# Tests that CommunityClusterer can be driven from a periodic caller,
# exercising the same pattern used by _start_community_clustering_loop in lifespan.py.
# We test the logic inline rather than importing lifespan (which has heavy deps).
# ---------------------------------------------------------------------------


async def _run_clustering_loop_once(mesh_db) -> list[str]:
    """Minimal replica of the loop body inside _start_community_clustering_loop.

    Runs one iteration: create clusterer, run it, return promoted IDs.
    This mirrors the production path in initialization/lifespan.py (#4834).
    """
    promoted = await CommunityClusterer(mesh_db).run()
    return promoted


@pytest.mark.asyncio
async def test_periodic_caller_promotes_anchors_on_connected_graph() -> None:
    """A scheduler-style caller creates CommunityClusterer per run and promotes centroids."""
    db = AsyncMock()
    db.fetch_edges = AsyncMock(
        return_value=_make_edges(
            [
                ("p1", "p2", 0.9),
                ("p2", "p3", 0.8),
                ("p1", "p3", 0.7),
            ]
        )
    )
    db.promote_to_anchor = AsyncMock()

    promoted = await _run_clustering_loop_once(db)

    assert len(promoted) == 1
    db.promote_to_anchor.assert_called_once_with(promoted[0])


@pytest.mark.asyncio
async def test_periodic_caller_noop_on_empty_graph() -> None:
    """A scheduler-style caller handles an empty graph gracefully — no promotions."""
    db = AsyncMock()
    db.fetch_edges = AsyncMock(return_value=[])
    db.promote_to_anchor = AsyncMock()

    promoted = await _run_clustering_loop_once(db)

    assert promoted == []
    db.promote_to_anchor.assert_not_called()


@pytest.mark.asyncio
async def test_periodic_caller_promotes_two_anchors_for_two_components() -> None:
    """Two disconnected components produce two anchor promotions per run."""
    db = AsyncMock()
    db.fetch_edges = AsyncMock(
        return_value=_make_edges(
            [
                ("a1", "a2", 1.0),
                ("a2", "a3", 1.0),
                ("a1", "a3", 1.0),
                ("b1", "b2", 1.0),
                ("b2", "b3", 1.0),
                ("b1", "b3", 1.0),
            ]
        )
    )
    db.promote_to_anchor = AsyncMock()

    promoted = await _run_clustering_loop_once(db)

    assert len(promoted) == 2
    assert db.promote_to_anchor.call_count == 2


# ---------------------------------------------------------------------------
# #13473: an unchanged mesh gets the same communities, whatever order its edges arrive in
# ---------------------------------------------------------------------------

#: Thirty equal-size triangles joined by weak cross edges -- the "many equal-sized
#: small communities" shape #13473 describes. Built from a fixed seed so the
#: fixture itself never varies.
_TRIANGLES = 30


def _mesh() -> list[dict]:
    import random

    rng = random.Random(7)
    pairs = []
    for c in range(_TRIANGLES):
        a, b, d = (f"n{c}_{i}" for i in range(3))
        pairs += [(a, b, 1.0), (b, d, 1.0), (a, d, 1.0)]
    for _ in range(25):
        pairs.append((f"n{rng.randrange(_TRIANGLES)}_0", f"n{rng.randrange(_TRIANGLES)}_1", 0.3))
    return _make_edges(pairs)


def _reordered(edges: list[dict], seed: int) -> list[dict]:
    """The same edges in another order, half of them with their endpoints swapped."""
    import random

    rng = random.Random(seed)
    out = [dict(e, from_node=e["to_node"], to_node=e["from_node"]) if rng.random() < 0.5 else dict(e) for e in edges]
    rng.shuffle(out)
    return out


def _assignment(edges: list[dict]) -> dict:
    from services.mesh_brain.community_clusterer import _build_graph, _detect_communities

    return _detect_communities(_build_graph(edges))


def test_the_fixture_has_many_equal_sized_communities() -> None:
    """FLOOR: without ties between equal sizes, the tiebreak below examines nothing."""
    sizes = {}
    for comm_id in _assignment(_mesh()).values():
        sizes[comm_id] = sizes.get(comm_id, 0) + 1
    most_common = max(list(sizes.values()).count(s) for s in set(sizes.values()))
    assert most_common >= 10, f"only {most_common} communities share a size: {sorted(sizes.values())}"


def test_an_unchanged_mesh_gets_the_same_assignment_in_any_edge_order() -> None:
    """fetch_edges orders by weight alone, so equal weights arrive in any order (#13473)."""
    expected = _assignment(_mesh())

    for seed in range(20):
        assert _assignment(_reordered(_mesh(), seed)) == expected, f"edge order {seed} regrouped the mesh"


def test_centroids_do_not_depend_on_edge_order() -> None:
    """The anchors promoted are what a run writes, so they must be order-free too."""
    expected = cluster_graph(_mesh())

    for seed in range(20):
        assert cluster_graph(_reordered(_mesh(), seed)) == expected


def test_community_ids_follow_size_then_membership() -> None:
    """Ids come from (-size, sorted members), not from the partitioner's enumeration."""
    members: dict[int, list[str]] = {}
    for node, comm_id in _assignment(_mesh()).items():
        members.setdefault(comm_id, []).append(str(node))
    keys = [(-len(members[i]), tuple(sorted(members[i]))) for i in sorted(members)]

    assert sorted(members) == list(range(len(members)))
    assert keys == sorted(keys)


def test_the_centroid_of_a_tied_community_does_not_depend_on_member_order() -> None:
    """The gap the edge-order tests above cannot see.

    `_reordered` varies edge order inside one process, where the string hash
    seed is fixed, so the whole suite above is blind to the one source of
    nondeterminism that actually survived: `louvain_communities` returns *sets*,
    and a list built by iterating one is in hash order, which differs between
    processes. `max(nodes, key=degree)` returns the first maximal element, so a
    degree tie resolved to whichever member happened to come first.

    Ties are the common case, not an edge case -- every node of a triangle has
    degree 2 -- so this decided real anchors. Permuting the member list directly
    reproduces across processes what a differing `PYTHONHASHSEED` would produce
    between them, without the cost of spawning one.
    """
    import itertools

    import networkx as nx

    from services.mesh_brain.community_clusterer import _pick_centroid

    triangle = nx.Graph()
    triangle.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")])
    assert len({triangle.degree(n) for n in "abc"}) == 1, "fixture must be fully tied on degree"

    picks = {_pick_centroid(triangle, list(perm)) for perm in itertools.permutations("abc")}

    assert picks == {"a"}, (
        f"the centroid of a degree-tied community depends on member order: {sorted(picks)}. "
        "Member order comes from set iteration, so the anchor differs between processes "
        "on an unchanged mesh (#13473)."
    )


def test_a_higher_degree_node_still_wins_over_the_name_tie_break() -> None:
    """The contrast pair: the tie-break must not have replaced the ranking.

    Without this, `_pick_centroid` could return `min(nodes)` outright and the
    permutation test above would still pass -- the cheapest way to satisfy a
    determinism check is to stop measuring what it was ranking.
    """
    import networkx as nx

    from services.mesh_brain.community_clusterer import _pick_centroid

    star = nx.Graph()
    star.add_edges_from([("z", "a"), ("z", "b"), ("z", "c")])

    assert _pick_centroid(star, ["a", "b", "c", "z"]) == "z", (
        "the highest-degree node lost to the alphabetical tie-break, so the centroid is "
        "no longer the most connected node"
    )
