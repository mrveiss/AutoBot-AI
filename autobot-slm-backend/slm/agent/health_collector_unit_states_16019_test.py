# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every reachable systemd state maps to something other than `unknown` (#16019).

Reported from the live deployment: `/slm/orchestration/per-node` showed redis,
slm-admin-ui and postgres as `unknown` while all three were healthy. Measured on
that node:

    postgresql            active/exited    <- oneshot wrapper, completed
    postgresql@16-main    active/running   <- the unit doing the work
    slm-admin-ui          active/exited    <- oneshot, completed
    redis-stack-server    active/running

Two independent defects produced the one symptom, and each is pinned below.

`unknown` must mean **the probe got no usable answer**. It must never mean
"systemd told me something this method has no branch for" -- those are opposite
situations that render identically, so a oneshot that finished successfully was
indistinguishable from a node nobody could reach.
"""

from unittest.mock import MagicMock, patch

from slm.agent.health_collector import HealthCollector


def _collector() -> HealthCollector:
    with patch.object(HealthCollector, "__init__", lambda self, *a, **k: None):
        return HealthCollector()


def test_a_completed_oneshot_is_not_reported_as_unknown():
    """`active (exited)` is systemd saying the unit SUCCEEDED.

    This is the regression: it matched no branch and fell through to `unknown`,
    which is what `slm-admin-ui` and the `postgresql` wrapper report on every
    healthy node.
    """
    status = _collector()._map_status_from_states("active", "exited")
    assert status != "unknown", "a successfully completed oneshot reported as unreadable"
    assert status == "completed"


def test_no_reachable_state_pair_maps_to_unknown():
    """The mapping must be total over what systemd actually emits.

    A floor on the pairs EXAMINED, not on the failures found: a shrunken table
    reports 'nothing maps to unknown' for the same reason a correct one does.
    """
    pairs = [
        ("active", "running"),
        ("active", "exited"),
        ("active", "waiting"),
        ("active", "mounted"),
        ("active", "plugged"),
        ("active", "listening"),
        ("activating", "start"),
        ("activating", "start-pre"),
        ("activating", "start-post"),
        ("activating", "auto-restart"),
        ("deactivating", "stop"),
        ("deactivating", "stop-sigterm"),
        ("inactive", "dead"),
        ("failed", "failed"),
    ]
    assert len(pairs) >= 14, "the table shrank -- the assertion below means nothing"
    collector = _collector()
    unreadable = [p for p in pairs if collector._map_status_from_states(*p) == "unknown"]
    assert not unreadable, (
        "these reachable systemd states report as `unknown`, which the UI cannot "
        f"distinguish from an unreachable node: {unreadable}"
    )


def test_a_failed_unit_is_still_failed():
    """The contrast. A mapping that answers 'running' to everything passes the
    test above while destroying the only signal the page exists to show."""
    collector = _collector()
    assert collector._map_status_from_states("failed", "failed") == "failed"
    assert collector._map_status_from_states("activating", "auto-restart") == "crash-loop"
    assert collector._map_status_from_states("inactive", "dead") == "stopped"


def test_a_templated_unit_is_reported_rather_than_discarded():
    """`postgresql@16-main.service` IS the running PostgreSQL on this fleet.

    Filtering every name containing `@` discarded the unit doing the work and
    kept `postgresql.service`, the oneshot wrapper that exits -- so the fleet's
    database reported `unknown` on a healthy node.
    """
    line = "postgresql@16-main.service loaded active running PostgreSQL Cluster 16-main"
    parsed = _collector()._parse_service_line(line)
    assert parsed is not None, "the running PostgreSQL instance was dropped by name shape"
    assert parsed["name"] == "postgresql@16-main"
    assert parsed["status"] == "running"


def test_a_phantom_unit_is_still_dropped():
    """The contrast for the filter: `not-found` must not become a reported service.

    `systemctl` answers `ActiveState=inactive` for a unit that does not exist --
    identical to one that is merely stopped -- so `LoadState` is the only field
    that separates them, and removing the `@` filter must not weaken this one.
    """
    line = "redis.service not-found inactive dead redis.service"
    assert _collector()._parse_service_line(line) is None
