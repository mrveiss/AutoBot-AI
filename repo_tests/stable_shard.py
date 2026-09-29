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

Balance is computed on **recorded seconds** (#17787). It used to be test count,
for a reason that confused magnitude with proportionality: the durations file
sums to ~338s while a head takes ~21 minutes, so recorded duration is indeed a
small fraction of real shard cost -- but a *weight* only has to be
**proportional** to cost, never equal to it, and the fixed part of a shard's
cost is the same for every shard and therefore creates no imbalance at all.

What the count-based balance actually produced, measured over the current
durations file at 12 splits:

    test count per shard   1813..2136   max/mean = 1.16   <- balanced
    recorded sec per shard      3..64   max/mean = 2.28   <- not
    observed wall clock (min)   5..13   max/mean = 1.59

So the proxy was balanced and the quantity that costs money was not. Balancing
on recorded milliseconds instead gives max/mean = 1.13 on seconds, and under
``wall ~= fixed + k*seconds`` predicts ~1.06 on wall clock. That model is fitted
from two summary statistics of one run and is therefore *consistent with* the
observations rather than validated by them -- the acceptance evidence is the
twelve durations of the next head on ``main``, not this paragraph.

Milliseconds as integers, not float seconds, so the sum is order-independent and
the table is byte-stable across platforms; a module present in the file but
totalling under a millisecond is floored to 1, because "fast" and "never
recorded" must not become the same weight.

Enabled only when ``--shard-splits`` is passed; otherwise this plugin does
nothing at all.
"""

from __future__ import annotations

import hashlib
import json
import math
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
    """Recorded test time per module in integer **milliseconds** (#17787).

    A missing or unreadable file yields an empty mapping — every module then
    weighs the same, which is still stable, just less balanced.

    Integer milliseconds rather than float seconds: the sum is then independent
    of iteration order and identical on every platform, which the on-disk shard
    table depends on. A non-numeric value contributes nothing rather than
    raising, because one malformed entry must not make the whole file unreadable
    and silently re-deal every module.
    """
    try:
        raw = json.loads(durations_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    weights: Dict[str, int] = {}
    for nodeid, seconds in raw.items():
        module = module_of(nodeid)
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            millis = 0
        elif not math.isfinite(seconds) or seconds < 0:
            # Rejected at the boundary, named, rather than handed to the balancer
            # (review). Python's JSON parser accepts `NaN` and `Infinity`, and
            # `int(round(...))` on either raises from inside this loop -- outside
            # the try above, so collection dies with a bare
            # "cannot convert float NaN to integer" naming nothing. A negative
            # duration is worse than a crash: it makes a negative bucket weight,
            # which the LPT pass consumes happily and silently mis-balances.
            raise ValueError(
                f"durations file {durations_path.name} has an unusable time for {module}: "
                f"{seconds!r}. A duration must be finite and non-negative."
            )
        else:
            millis = int(round(seconds * 1000))
        weights[module] = weights.get(module, 0) + millis
    # Present-but-fast is not absent. A module whose recorded total rounds to
    # zero would otherwise weigh exactly what a module the file has never seen
    # weighs, and the two are different facts.
    return {module: max(total, 1) for module, total in weights.items()}


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
