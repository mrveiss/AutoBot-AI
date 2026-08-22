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
    bucket_of,
    build_bucket_table,
    load_module_weights,
    module_of,
    shard_of,
)

SPLITS = 12


def _weights(n_modules=400, tests_per_module=8):
    return {f"pkg/mod_{i:04d}_test.py": tests_per_module for i in range(n_modules)}


def _assignment(collected, table, splits=SPLITS):
    """Shard per collected module, through a table that is already built.

    Mirrors production: the table comes from the durations file, the modules
    come from whatever this run collected. Keeping the two apart is the whole
    mechanism — see `TestStability`.
    """
    del splits  # the table already encodes it
    return {m: shard_of(m, table, DEFAULT_BUCKETS) for m in collected}


class TestStability:
    """The property the whole change exists for.

    **The durations file and the collected set are different inputs**, and only
    the first may feed the table. A PR that adds tests changes what is
    *collected*; it does not touch `.test_durations`. That is precisely why the
    assignment survives it.

    An earlier version of these tests rebuilt the table from the mutated
    collection and failed all four assertions — correctly. Rebuilding from what
    was just collected destroys every property below, because adding a module
    changes the weights, which changes the table, which re-deals everything. The
    tests were wrong, not the implementation; this comment exists so the same
    mistake is not made a third time.
    """

    def test_adding_a_module_moves_no_existing_module(self):
        table = build_bucket_table(_weights(), SPLITS, DEFAULT_BUCKETS)
        base = _assignment(_weights(), table)

        collected = dict(_weights())
        collected["pkg/brand_new_test.py"] = 8
        after = _assignment(collected, table)

        moved = [m for m in _weights() if after[m] != base[m]]
        assert moved == [], f"{len(moved)} existing modules changed shard when one module was added"

    def test_growing_a_module_moves_no_other_module(self):
        table = build_bucket_table(_weights(), SPLITS, DEFAULT_BUCKETS)
        base = _assignment(_weights(), table)

        collected = dict(_weights())
        victim = "pkg/mod_0007_test.py"
        collected[victim] += 50
        after = _assignment(collected, table)

        moved = [m for m in _weights() if m != victim and after[m] != base[m]]
        assert moved == [], f"{len(moved)} unrelated modules changed shard when one module grew"

    def test_removing_a_module_moves_no_other_module(self):
        table = build_bucket_table(_weights(), SPLITS, DEFAULT_BUCKETS)
        base = _assignment(_weights(), table)

        collected = dict(_weights())
        del collected["pkg/mod_0100_test.py"]
        after = _assignment(collected, table)

        moved = [m for m in collected if after[m] != base[m]]
        assert moved == [], f"{len(moved)} modules changed shard when one module was removed"

    def test_a_module_keeps_its_shard_when_collection_is_partial(self):
        """A checkout missing optional deps collects fewer modules.

        Module-level `importorskip` means those tests are never collected, so
        under contiguous chunking the same `--group N` named different tests
        locally than on the runner — measured 2,096 against 1,991 for one
        commit. That is why "passes locally" could not clear a shard failure.
        Here the assignment does not consult the collected set at all.
        """
        table = build_bucket_table(_weights(), SPLITS, DEFAULT_BUCKETS)
        full = _assignment(_weights(), table)
        partial = _assignment({m: w for i, (m, w) in enumerate(_weights().items()) if i % 3}, table)

        for module in partial:
            assert partial[module] == full[module], f"{module} moved shard when collection was partial"

    def test_a_module_absent_from_durations_still_gets_a_shard(self):
        """15% of collected tests have no recorded duration. They must still be
        assigned, and by the same rule — the table is consulted by hash, so a
        module the durations file has never seen is not a special case."""
        table = build_bucket_table(_weights(), SPLITS, DEFAULT_BUCKETS)

        shard = shard_of("pkg/never_measured_test.py", table, DEFAULT_BUCKETS)

        assert 0 <= shard < SPLITS

    def test_regenerating_durations_IS_allowed_to_re_deal(self):
        """The one operation that legitimately reshuffles.

        Named here so it is a known, deliberate act rather than a surprise: if
        this ever stops being true the table has become independent of its own
        input, which would mean the balancing pass is not running.
        """
        table = build_bucket_table(_weights(), SPLITS, DEFAULT_BUCKETS)
        regenerated = build_bucket_table(
            {m: (w + 40 if i % 2 else w) for i, (m, w) in enumerate(_weights().items())},
            SPLITS,
            DEFAULT_BUCKETS,
        )

        assert table != regenerated, "a materially different durations file should re-balance the table"


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
        assignment = _assignment(weights, build_bucket_table(weights, SPLITS, DEFAULT_BUCKETS))
        assert set(assignment) == set(weights)
        assert all(0 <= s < SPLITS for s in assignment.values())

    def test_the_union_of_all_shards_is_the_whole_set(self):
        weights = _weights()
        assignment = _assignment(weights, build_bucket_table(weights, SPLITS, DEFAULT_BUCKETS))
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
        assignment = _assignment(weights, build_bucket_table(weights, SPLITS, DEFAULT_BUCKETS))
        load = [0] * SPLITS
        for module, shard in assignment.items():
            load[shard] += weights[module]
        assert max(load) / max(min(load), 1) < 1.5, f"shard load spread too wide: {sorted(load)}"


class TestDurationsFileHandling:
    def test_a_missing_durations_file_still_assigns(self, tmp_path):
        assert load_module_weights(tmp_path / "nope.json") == {}
        table = build_bucket_table({}, SPLITS, DEFAULT_BUCKETS)
        assert len(table) == DEFAULT_BUCKETS
        # `<=` was the original assertion and it holds when ONE shard is used,
        # so the degenerate case read as covered while being untested (#14802).
        assert set(table) == set(range(SPLITS)), (
            "every shard must receive buckets even with no durations data; "
            "otherwise the unused shards collect nothing and the work lands on one"
        )

    @pytest.mark.parametrize(
        "weights",
        [
            pytest.param({}, id="no-durations"),
            pytest.param({"autobot-slm-backend/only_test.py": 100}, id="one-module"),
            pytest.param({f"pkg/m{i}_test.py": 10 * (i + 1) for i in range(5)}, id="five-modules"),
        ],
    )
    def test_every_shard_is_reachable_however_thin_the_durations(self, weights):
        """A thin durations file must not make most shards unreachable.

        Zero-weight buckets do not move `shard_load`, so a load-only tie-break
        hands every one of them to the same lowest-index shard. The shards after
        it then receive nothing — and stay unreachable by any file that could
        later be added, since the mapping is by hash. #14648 is what activates
        this algorithm in CI, and the SLM step's exit-5 tolerance would turn the
        resulting empty shards into green rather than red.
        """
        table = build_bucket_table(weights, SPLITS, DEFAULT_BUCKETS)
        assert set(table) == set(range(SPLITS)), f"only {len(set(table))} of {SPLITS} shards received buckets"

    def test_a_thin_durations_file_does_not_strand_future_modules(self):
        """The collapse is structural: unused shards can never be reached again."""
        table = build_bucket_table({"autobot-slm-backend/only_test.py": 100}, SPLITS, DEFAULT_BUCKETS)
        landed = {shard_of(f"future/mod{i}_test.py", table, DEFAULT_BUCKETS) for i in range(5000)}
        assert landed == set(range(SPLITS)), (
            f"5000 hypothetical new modules reached only shards {sorted(landed)} — "
            "the rest cannot be reached by any file that could be added"
        )

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
