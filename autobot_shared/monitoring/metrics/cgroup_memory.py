# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""cgroup v2 memory pressure metrics (#13765).

`autobot-backend` sat pinned at an 8 GiB `MemoryHigh` watermark with
`memory.events high` at 21,052, the process in `STAT=D`, and `/health` timing
out — while `systemctl` reported `active` for the entire window. `MemoryHigh`
does not kill; it applies escalating reclaim pressure. So the service never
crashed, never restarted, never entered `failed`, and every liveness signal kept
saying it was fine while it stopped making progress.

Memory *usage* cannot distinguish that state from a healthy one: a throttled
cgroup reports normal-looking `memory.current` (it is held at the watermark by
design) and its health endpoint either answers slowly or not at all. The one
signal that separates them is the **reclaim counter** — `memory.events high`
increments every time the kernel throttles the cgroup, and it is monotonic. That
is what these metrics export and what the alert rules fire on.

The limits themselves are exported too, because the second half of #13765 is that
nobody knew they were there: they came from `systemctl set-property`, which
writes to `/etc/systemd/system.control/`, and nothing in the unit template, the
ansible role, or the repo mentions them. A limit no artifact records is a limit
that behaves differently on every host, so it needs to be visible in the same
place the pressure is.

Sampled at scrape time via a custom collector rather than recorded at event time:
there is no event to hook — the kernel updates these files continuously — and a
polling task would add a staleness window for no benefit.
"""

from __future__ import annotations

from pathlib import Path

from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# cgroup v2 mount point. Overridable so tests can point at a fixture tree.
DEFAULT_CGROUP_ROOT = Path("/sys/fs/cgroup")

# Where `systemctl set-property` writes runtime overrides. A drop-in here is
# invisible to the repo: it is not in the unit template and not in any role, so a
# fresh install of the same commit gets different limits (#13765).
SYSTEMD_CONTROL_ROOT = Path("/etc/systemd/system.control")

# memory.events keys worth exporting. `high` is the reclaim counter — the signal
# this module exists for. `max` counts hard-cap hits (allocation failures /
# OOM-kill territory), `oom` and `oom_kill` are the terminal cases.
_EVENT_KEYS = ("low", "high", "max", "oom", "oom_kill")

# memory.high / memory.max hold the literal string "max" when unlimited. Exported
# as -1 rather than +Inf so a "limit is set" query is a simple `>= 0` and does not
# depend on how the scraper renders infinity.
_UNLIMITED = -1.0


def _read_int(path: Path) -> int | None:
    """Read a single-integer cgroup file, or None when absent/unreadable."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if raw == "max":
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("cgroup: %s holds %r, not an integer", path, raw[:40])
        return None


def read_memory_events(cgroup_dir: Path) -> dict[str, int]:
    """Parse `memory.events` into a dict, empty when the file is unavailable.

    Format is one `key value` pair per line. Unknown keys are kept: a future
    kernel adding a counter should not need a change here to be visible.
    """
    try:
        raw = (cgroup_dir / "memory.events").read_text(encoding="utf-8")
    except OSError:
        return {}

    events: dict[str, int] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            events[parts[0]] = int(parts[1])
        except ValueError:
            continue
    return events


def has_out_of_band_limits(unit: str, control_root: Path = SYSTEMD_CONTROL_ROOT) -> bool:
    """True when *unit* carries a `systemctl set-property` drop-in (#13765).

    These survive deploys — nothing in the update path touches
    `system.control/` — so they outlive any attempt to fix the problem in the
    ansible role, and they make this host behave unlike a clean install of the
    same commit.
    """
    try:
        return (control_root / f"{unit}.d").is_dir()
    except OSError:
        return False


class CgroupMemoryCollector(Collector):
    """Export cgroup v2 memory pressure for a set of systemd units.

    Registered as a custom collector, so every scrape reads the live kernel
    counters. No background task, and no window in which the exported value and
    the cgroup disagree.
    """

    def __init__(
        self,
        units: list[str],
        cgroup_root: Path = DEFAULT_CGROUP_ROOT,
        control_root: Path = SYSTEMD_CONTROL_ROOT,
    ) -> None:
        self.units = units
        self.cgroup_root = cgroup_root
        self.control_root = control_root

    def _unit_dir(self, unit: str) -> Path:
        """cgroup path for a systemd system-slice service."""
        return self.cgroup_root / "system.slice" / unit

    def collect(self):  # noqa: C901 - one branch per exported metric, flat
        events = GaugeMetricFamily(
            "autobot_cgroup_memory_events",
            "cgroup v2 memory.events counters; `high` is the reclaim counter that "
            "rises while a cgroup is throttled but still reports active (#13765)",
            labels=["unit", "event"],
        )
        current = GaugeMetricFamily(
            "autobot_cgroup_memory_current_bytes",
            "Current cgroup memory usage in bytes",
            labels=["unit"],
        )
        high = GaugeMetricFamily(
            "autobot_cgroup_memory_high_bytes",
            "MemoryHigh throttling watermark in bytes; -1 when unlimited",
            labels=["unit"],
        )
        maximum = GaugeMetricFamily(
            "autobot_cgroup_memory_max_bytes",
            "MemoryMax hard limit in bytes; -1 when unlimited",
            labels=["unit"],
        )
        undeclared = GaugeMetricFamily(
            "autobot_cgroup_memory_limits_out_of_band",
            "1 when the unit has a systemctl set-property drop-in, i.e. limits no "
            "repo artifact records and a fresh install would not reproduce (#13765)",
            labels=["unit"],
        )

        for unit in self.units:
            unit_dir = self._unit_dir(unit)
            if not unit_dir.is_dir():
                # Not running here, or not cgroup v2 — nothing to say, and saying
                # something would be worse than silence.
                continue

            for key, value in read_memory_events(unit_dir).items():
                events.add_metric([unit, key], value)

            for metric, filename in (
                (current, "memory.current"),
                (high, "memory.high"),
                (maximum, "memory.max"),
            ):
                value = _read_int(unit_dir / filename)
                if value is None and filename == "memory.current":
                    continue
                metric.add_metric([unit], _UNLIMITED if value is None else value)

            undeclared.add_metric([unit], 1.0 if has_out_of_band_limits(unit, self.control_root) else 0.0)

        yield events
        yield current
        yield high
        yield maximum
        yield undeclared


__all__ = [
    "CgroupMemoryCollector",
    "read_memory_events",
    "has_out_of_band_limits",
    "DEFAULT_CGROUP_ROOT",
    "SYSTEMD_CONTROL_ROOT",
]
