# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Duplicate clusters: one row per group of matching blocks, every location listed (#22157).

k identical blocks used to be reported as k(k-1)/2 pairs, and the same file pair
once per matching block. A cluster is the group itself; adjacent clusters shared
by the same files are merged into one range.

Kinds, strongest first:
  exact       equal after comment and whitespace normalization only
  structural  equal only once string literals are erased -- never reported as 100%
  similar     token-set similarity below identity (the fuzzy pass)
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

KIND_EXACT = "exact"
KIND_STRUCTURAL = "structural"
KIND_SIMILAR = "similar"

# A structural match is high-confidence but is not equal code, so it is below 1.0.
STRUCTURAL_SIMILARITY = 0.95
# Two blocks of one file pair are adjacent when no more than one blank line separates them.
ADJACENT_LINE_GAP = 2


@dataclass(frozen=True)
class DuplicateLocation:
    """One place a duplicated block lives."""

    file: str
    start_line: int
    end_line: int


@dataclass
class DuplicateCluster:
    """A group of matching blocks and every location they occupy."""

    kind: str
    similarity: float
    line_count: int
    locations: List[DuplicateLocation]
    code_snippet: str = ""

    # The first two locations, under the names the pair-shaped consumers read.
    @property
    def file1(self) -> str:
        return self.locations[0].file

    @property
    def file2(self) -> str:
        return self.locations[1].file

    @property
    def start_line1(self) -> int:
        return self.locations[0].start_line

    @property
    def end_line1(self) -> int:
        return self.locations[0].end_line

    @property
    def start_line2(self) -> int:
        return self.locations[1].start_line

    @property
    def end_line2(self) -> int:
        return self.locations[1].end_line

    def to_dict(self, path_fn: Optional[Callable[[str], str]] = None) -> Dict[str, Any]:
        """JSON row; ``path_fn`` maps an absolute path to the one displayed."""
        show = path_fn or (lambda path: path)
        return {
            "kind": self.kind,
            "similarity": round(self.similarity * 100, 1),
            "lines": self.line_count,
            "code_snippet": self.code_snippet[:200],
            "locations": [
                {"file": show(loc.file), "start_line": loc.start_line, "end_line": loc.end_line}
                for loc in self.locations
            ],
            "file1": show(self.file1),
            "file2": show(self.file2),
            "start_line1": self.start_line1,
            "end_line1": self.end_line1,
            "start_line2": self.start_line2,
            "end_line2": self.end_line2,
        }


def _spans_files(blocks: Sequence[Any]) -> bool:
    return len({block.file_path for block in blocks}) > 1


def _cluster_of(kind: str, similarity: float, blocks: Sequence[Any]) -> DuplicateCluster:
    places = {DuplicateLocation(b.file_path, b.start_line, b.end_line) for b in blocks}
    return DuplicateCluster(
        kind=kind,
        similarity=similarity,
        line_count=max(b.line_count for b in blocks),
        locations=sorted(places, key=lambda loc: (loc.file, loc.start_line)),
        code_snippet=blocks[0].content[:200],
    )


def find_identical_clusters(blocks: Iterable[Any]) -> List[DuplicateCluster]:
    """Exact clusters, plus a structural cluster where the match needed string erasure.

    A group of structurally equal blocks whose exact hashes differ is reported once
    as ``structural`` with all its locations; each subgroup that is exactly equal is
    additionally an ``exact`` cluster. Clusters must span at least two files.
    """
    by_structure: Dict[str, List[Any]] = defaultdict(list)
    for block in blocks:
        by_structure[block.content_hash].append(block)
    clusters: List[DuplicateCluster] = []
    for group in by_structure.values():
        if not _spans_files(group):
            continue
        by_text: Dict[str, List[Any]] = defaultdict(list)
        for block in group:
            by_text[block.exact_hash].append(block)
        clusters.extend(_cluster_of(KIND_EXACT, 1.0, same) for same in by_text.values() if _spans_files(same))
        if len(by_text) > 1:
            clusters.append(_cluster_of(KIND_STRUCTURAL, STRUCTURAL_SIMILARITY, group))
    return clusters


def _find_root(parent: Dict[Tuple[str, int], Tuple[str, int]], key: Tuple[str, int]) -> Tuple[str, int]:
    while parent.setdefault(key, key) != key:
        parent[key] = parent[parent[key]]
        key = parent[key]
    return key


def cluster_similar_pairs(pairs: Iterable[Any]) -> List[DuplicateCluster]:
    """Connected components of fuzzy pairs; a component's similarity is its weakest link."""
    parent: Dict[Tuple[str, int], Tuple[str, int]] = {}
    places: Dict[Tuple[str, int], DuplicateLocation] = {}
    listed = list(pairs)
    for pair in listed:
        first, second = (pair.file1, pair.start_line1), (pair.file2, pair.start_line2)
        places[first] = DuplicateLocation(pair.file1, pair.start_line1, pair.end_line1)
        places[second] = DuplicateLocation(pair.file2, pair.start_line2, pair.end_line2)
        parent[_find_root(parent, first)] = _find_root(parent, second)
    members: Dict[Tuple[str, int], List[DuplicateLocation]] = defaultdict(list)
    for key, place in places.items():
        members[_find_root(parent, key)].append(place)
    weakest: Dict[Tuple[str, int], Any] = {}
    for pair in listed:
        root = _find_root(parent, (pair.file1, pair.start_line1))
        if root not in weakest or pair.similarity < weakest[root].similarity:
            weakest[root] = pair
    return [
        DuplicateCluster(
            kind=KIND_SIMILAR,
            similarity=weakest[root].similarity,
            line_count=weakest[root].line_count,
            locations=sorted(locs, key=lambda loc: (loc.file, loc.start_line)),
            code_snippet=weakest[root].code_snippet,
        )
        for root, locs in members.items()
        if len({loc.file for loc in locs}) > 1
    ]


def _follows(prev: DuplicateCluster, cur: DuplicateCluster) -> bool:
    return all(0 <= b.start_line - a.end_line <= ADJACENT_LINE_GAP for a, b in zip(prev.locations, cur.locations))


def _join(prev: DuplicateCluster, cur: DuplicateCluster) -> DuplicateCluster:
    return DuplicateCluster(
        kind=prev.kind,
        similarity=min(prev.similarity, cur.similarity),
        line_count=prev.line_count + cur.line_count,
        locations=[DuplicateLocation(a.file, a.start_line, b.end_line) for a, b in zip(prev.locations, cur.locations)],
        code_snippet=prev.code_snippet,
    )


def merge_adjacent_clusters(clusters: Iterable[DuplicateCluster]) -> List[DuplicateCluster]:
    """Merge clusters of one kind and one set of files whose blocks are adjacent in every file.

    Only clusters with a single location per file merge; their ranges then line up.
    """
    merged: List[DuplicateCluster] = []
    chains: Dict[Tuple[str, Tuple[str, ...]], List[DuplicateCluster]] = defaultdict(list)
    for cluster in clusters:
        files = tuple(loc.file for loc in cluster.locations)
        if len(set(files)) == len(files):
            chains[(cluster.kind, files)].append(cluster)
        else:
            merged.append(cluster)
    for members in chains.values():
        run: List[DuplicateCluster] = []
        for cluster in sorted(members, key=lambda c: c.locations[0].start_line):
            if run and _follows(run[-1], cluster):
                run[-1] = _join(run[-1], cluster)
            else:
                run.append(cluster)
        merged.extend(run)
    return merged
