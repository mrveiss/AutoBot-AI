# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Stable, module-level shard assignment (#14111).

pytest-split's ``duration_based_chunks`` cuts the *collected list* into
contiguous chunks. That keeps whole modules in one shard — the property
``--dist loadscope`` depends on — but it makes a shard's membership a function
of the collected list's order **and** membership. Two consequences, both
observed:

* Adding one test file shifts every downstream boundary, so every later shard
  gets different neighbours. A PR is reddened by a failure nowhere near its
  diff, because the shuffle put a state-polluting module next to a susceptible
  one. Measured: adding a single module re-deals ~1019 of 1283 modules.
* A checkout missing optional dependencies collects a different set (module
  level ``importorskip`` means those tests are never collected), so the same
  ``--group N`` names different tests locally than on the runner. Measured
  2,096 items locally against 1,991 on the runner for the same commit — which
  is why shard failures could not be reproduced.

This assigns **whole modules** instead:

1. hash the module path into one of ``buckets`` buckets (default 512);
2. map buckets to shards with a greedy longest-processing-time pass over the
   bucket weights read from the durations file.

Step 2 reads only the durations file, which a PR adding tests does not modify.
So a module's shard depends on its own path and on a file nobody edits
casually — never on what else was collected. Adding, removing or growing a
module moves **no** other module. Measured across 50 trials: zero.

Balance is computed on **test count**, not recorded seconds. The durations file
sums to ~338s while a shard takes minutes, so recorded duration describes a
small fraction of real shard cost (import and collection dominate); balancing
on it optimises the wrong quantity. Test count gives 1.18x spread between the
lightest and heaviest shard.

Enabled only when ``--shard-splits`` is passed; otherwise this plugin does
nothing at all.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

#: Buckets hashed into before mapping to shards. Well above the shard count so
#: the LPT pass has enough granularity to balance; changing it re-deals every
#: module, so treat it as part of the on-disk contract.
DEFAULT_BUCKETS = 512


def module_of(nodeid: str) -> str:
    """The file part of a node id — everything before the first ``::``."""
    return nodeid.split("::", 1)[0]


def bucket_of(module: str, buckets: int) -> int:
    """Stable bucket for *module*. Depends on the path and nothing else."""
    digest = hashlib.sha256(module.encode("utf-8")).hexdigest()
    return int(digest, 16) % buckets


def load_module_weights(durations_path: Path) -> Dict[str, int]:
    """Test count per module, read from a pytest-split durations file.

    A missing or unreadable file yields an empty mapping — every module then
    weighs the same, which is still stable, just less balanced.
    """
    try:
        raw = json.loads(durations_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    weights: Dict[str, int] = {}
    for nodeid in raw:
        weights[module_of(nodeid)] = weights.get(module_of(nodeid), 0) + 1
    return weights


def build_bucket_table(weights: Dict[str, int], splits: int, buckets: int) -> List[int]:
    """Map each bucket to a shard, balancing total weight across shards.

    Greedy longest-processing-time over *bucket* weights. The instability that
    makes LPT unusable over modules directly does not apply here: the input is
    the durations file, not the collected set, so the table only changes when
    someone regenerates durations deliberately.
    """
    bucket_weight = [0] * buckets
    for module, weight in weights.items():
        bucket_weight[bucket_of(module, buckets)] += weight

    shard_load = [0] * splits
    # Bucket counts break the tie that load alone cannot. A zero-weight bucket
    # adds nothing to `shard_load`, so without this the same lowest-index shard
    # wins every subsequent tie and every weightless bucket piles onto it — with
    # an empty durations file all 512 buckets land on shard 0, and the remaining
    # shards become unreachable by any file that could ever be added, not merely
    # empty today (#14802).
    shard_buckets = [0] * splits
    table = [0] * buckets
    for bucket in sorted(range(buckets), key=lambda b: (-bucket_weight[b], b)):
        target = min(range(splits), key=lambda s: (shard_load[s], shard_buckets[s], s))
        table[bucket] = target
        shard_load[target] += bucket_weight[bucket]
        shard_buckets[target] += 1
    return table


def shard_of(module: str, table: List[int], buckets: int) -> int:
    """The 0-based shard *module* belongs to."""
    return table[bucket_of(module, buckets)]


# ---------------------------------------------------------------------------
# pytest plugin
# ---------------------------------------------------------------------------


def pytest_addoption(parser) -> None:
    group = parser.getgroup("stable-shard")
    group.addoption("--shard-splits", type=int, default=0, help="Total shards (#14111). 0 disables sharding.")
    group.addoption("--shard-group", type=int, default=1, help="1-based shard to run.")
    group.addoption(
        "--shard-durations",
        default=".test_durations",
        help="Durations file used to balance buckets across shards.",
    )


def pytest_collection_modifyitems(config, items) -> None:
    """Deselect everything outside this shard, whole modules at a time."""
    splits = config.getoption("--shard-splits")
    if not splits or splits < 1:
        return

    group = config.getoption("--shard-group")
    if not 1 <= group <= splits:
        raise ValueError(f"--shard-group must be within 1..{splits}, got {group}")

    durations = Path(config.rootpath) / config.getoption("--shard-durations")
    table = build_bucket_table(load_module_weights(durations), splits, DEFAULT_BUCKETS)

    selected, deselected = [], []
    for item in items:
        target = shard_of(module_of(item.nodeid), table, DEFAULT_BUCKETS)
        (selected if target == group - 1 else deselected).append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected
