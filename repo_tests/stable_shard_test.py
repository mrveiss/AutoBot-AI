# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Properties the shard assignment must hold (#14111).

The defect being fixed is not a wrong answer, it is an *unstable* one: with
contiguous chunking, adding one test file re-deals every later shard, so a PR
goes red on a failure nowhere near its diff. Stability is therefore the property
under test here, and it is asserted as an invariant rather than measured once
and quoted.
"""

import json

import pytest

from repo_tests.stable_shard import (
    DEFAULT_BUCKETS,
    build_bucket_table,
    bucket_of,
    load_module_weights,
    module_of,
    shard_of,
)

SPLITS = 12


def _weights(n_modules=400, tests_per_module=8):
    return {f"pkg/mod_{i:04d}_test.py": tests_per_module for i in range(n_modules)}


def _assignment(weights, splits=SPLITS):
    table = build_bucket_table(weights, splits, DEFAULT_BUCKETS)
    return {m: shard_of(m, table, DEFAULT_BUCKETS) for m in weights}


class TestStability:
    """The property the whole change exists for."""

    def test_adding_a_module_moves_no_existing_module(self):
        base_w = _weights()
        base = _assignment(base_w)

        grown = dict(base_w)
        grown["pkg/brand_new_test.py"] = 8
        after = _assignment(grown)

        moved = [m for m in base_w if after[m] != base[m]]
        assert moved == [], f"{len(moved)} existing modules changed shard when one module was added"

    def test_growing_a_module_moves_no_other_module(self):
        base_w = _weights()
        base = _assignment(base_w)

        grown = dict(base_w)
        victim = "pkg/mod_0007_test.py"
        grown[victim] += 50
        after = _assignment(grown)

        moved = [m for m in base_w if m != victim and after[m] != base[m]]
        assert moved == [], f"{len(moved)} unrelated modules changed shard when one module grew"

    def test_removing_a_module_moves_no_other_module(self):
        base_w = _weights()
        base = _assignment(base_w)

        shrunk = dict(base_w)
        del shrunk["pkg/mod_0100_test.py"]
        after = _assignment(shrunk)

        moved = [m for m in shrunk if after[m] != base[m]]
        assert moved == [], f"{len(moved)} modules changed shard when one module was removed"

    def test_a_module_keeps_its_shard_when_collection_is_partial(self):
        """A checkout missing optional deps collects fewer modules.

        Under contiguous chunking that changed which tests a group named, so
        "passes locally" could not clear a shard failure. Here the assignment
        does not depend on what was collected at all.
        """
        base_w = _weights()
        full = _assignment(base_w)
        partial = _assignment({m: w for i, (m, w) in enumerate(base_w.items()) if i % 3})

        for module in partial:
            assert partial[module] == full[module], f"{module} moved shard when collection was partial"


class TestWholeModulesStayTogether:
    def test_every_test_in_a_module_lands_in_one_shard(self):
        weights = _weights()
        table = build_bucket_table(weights, SPLITS, DEFAULT_BUCKETS)
        for module in weights:
            ids = [f"{module}::test_{i}" for i in range(5)]
            shards = {shard_of(module_of(i), table, DEFAULT_BUCKETS) for i in ids}
            assert len(shards) == 1, f"{module} was split across shards {shards}"


class TestPartition:
    def test_every_module_lands_in_exactly_one_shard_and_none_is_lost(self):
        weights = _weights()
        assignment = _assignment(weights)
        assert set(assignment) == set(weights)
        assert all(0 <= s < SPLITS for s in assignment.values())

    def test_the_union_of_all_shards_is_the_whole_set(self):
        weights = _weights()
        assignment = _assignment(weights)
        union = set()
        for shard in range(SPLITS):
            union |= {m for m, s in assignment.items() if s == shard}
        assert union == set(weights)


class TestBalance:
    def test_the_heaviest_shard_is_within_a_bounded_factor_of_the_lightest(self):
        """Guards the reason a stable-but-useless assignment is not acceptable.

        A pure hash is perfectly stable and gave 2.97x on real data; the bucket
        table exists to get balance back. The bound is asserted so a future
        change to bucketing cannot quietly unbalance CI — the slowest shard
        gates the whole job.
        """
        weights = {f"pkg/mod_{i:04d}_test.py": (i % 37) + 1 for i in range(1200)}
        assignment = _assignment(weights)
        load = [0] * SPLITS
        for module, shard in assignment.items():
            load[shard] += weights[module]
        assert max(load) / max(min(load), 1) < 1.5, f"shard load spread too wide: {sorted(load)}"


class TestDurationsFileHandling:
    def test_a_missing_durations_file_still_assigns(self, tmp_path):
        assert load_module_weights(tmp_path / "nope.json") == {}
        table = build_bucket_table({}, SPLITS, DEFAULT_BUCKETS)
        assert len(table) == DEFAULT_BUCKETS
        assert set(table) <= set(range(SPLITS))

    def test_a_corrupt_durations_file_does_not_raise(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert load_module_weights(bad) == {}

    def test_weights_count_tests_per_module(self, tmp_path):
        path = tmp_path / "d.json"
        path.write_text(
            json.dumps({"a_test.py::test_x": 0.1, "a_test.py::test_y": 0.2, "b_test.py::test_z": 0.3}),
            encoding="utf-8",
        )
        assert load_module_weights(path) == {"a_test.py": 2, "b_test.py": 1}


class TestNodeIdParsing:
    @pytest.mark.parametrize(
        "nodeid,expected",
        [
            ("pkg/x_test.py::test_a", "pkg/x_test.py"),
            ("pkg/x_test.py::TestC::test_a", "pkg/x_test.py"),
            ("pkg/x_test.py::test_a[param::with::colons]", "pkg/x_test.py"),
            ("pkg/x_test.py", "pkg/x_test.py"),
        ],
    )
    def test_the_module_is_everything_before_the_first_separator(self, nodeid, expected):
        assert module_of(nodeid) == expected

    def test_bucketing_depends_only_on_the_path(self):
        assert bucket_of("a/b_test.py", DEFAULT_BUCKETS) == bucket_of("a/b_test.py", DEFAULT_BUCKETS)
        assert bucket_of("a/b_test.py", DEFAULT_BUCKETS) < DEFAULT_BUCKETS
