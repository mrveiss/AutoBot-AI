# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Value pin for ``CategoryDefaults`` (#14047 review).

Every new assertion this issue's fix added elsewhere in the tree reads
``assert x == CategoryDefaults.GENERAL`` — if someone renames the constant's
*value* (e.g. ``GENERAL: str = "generic"``), the production call site and
every one of those assertions move together and stay green, silently
changing persisted KB metadata, an audit-log field, a Prometheus label, and
a MAP-Elites grid cell key. This file pins the literal independently, the
same role ``ssot-parity.spec.ts`` plays for the TypeScript mirror
(``CATEGORY_DEFAULTS`` in ``src/config/ssot-config.ts``) -- both read the
value as a hard string, not via the symbol under test.
"""

from autobot_shared.ssot_constants import CategoryDefaults


def test_general_value_is_pinned():
    assert CategoryDefaults.GENERAL == "general"


def test_unknown_value_is_pinned():
    assert CategoryDefaults.UNKNOWN == "unknown"


def test_search_mode_hybrid_value_is_pinned():
    assert CategoryDefaults.SEARCH_MODE_HYBRID == "hybrid"


def test_ttl_constants_equal_the_literals_they_replaced() -> None:
    """#14181: every literal replaced by a constant must still be that value.

    Twelve `.setex()`/`.expire()`/`ttl=` call sites moved from literals to these
    names. A constant that later drifts changes a production TTL silently at
    every one of them — the failure would be a cache expiring at the wrong time,
    with nothing pointing back at the edit that caused it.

    `TTL_WORKING_MEMORY_DEFAULT` has drifted once already (to `TTL_24_HOURS`
    during the #7440 consolidation, restored in #11834), which is why this is
    asserted rather than assumed.
    """
    from autobot_shared.ssot_constants import (
        TTL_1_HOUR,
        TTL_1_MINUTE,
        TTL_2_HOURS,
        TTL_5_MINUTES,
        TTL_24_HOURS,
        TTL_30_DAYS,
    )

    assert TTL_1_MINUTE == 60
    assert TTL_5_MINUTES == 300
    assert TTL_1_HOUR == 3600
    assert TTL_2_HOURS == 7200
    assert TTL_24_HOURS == 86400
    assert TTL_30_DAYS == 2592000


def test_no_tracked_python_file_carries_a_literal_ttl() -> None:
    """The invariant, not the twelve instances.

    Asserting the specific call sites would pass the day someone adds a
    thirteenth. This runs the real checker over the tracked tree, so it fails
    on any new literal TTL in a `.setex()`/`.expire()`/`.pexpire()`/`ttl=` call.

    Known gap, tracked separately: the checker does not see `.set(ex=N)`, the
    redis-py native kwarg. This test inherits that blind spot rather than
    hiding it.
    """
    import subprocess  # nosec B404  # fixed argv, no shell
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    listing = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"], cwd=str(repo), capture_output=True, text=True
    )
    assert listing.returncode == 0, "git ls-files failed — refusing to report clean"
    files = listing.stdout.split()
    assert files, "git ls-files listed nothing — refusing to report clean"

    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["python3", "pipeline-scripts/check_no_literal_ttl_seconds.py", *files],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"literal TTL(s) found:\n{result.stdout}{result.stderr}"
