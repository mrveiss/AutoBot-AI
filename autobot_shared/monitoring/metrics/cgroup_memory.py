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
cgroup is held at its watermark by design. The one signal that separates them is
the **reclaim counter** — `memory.events high` increments every time the kernel
throttles the cgroup, and it is monotonic.

The limits themselves are exported too, because the second half of #13765 is that
nobody knew they were there: they came from `systemctl set-property`, which
writes drop-ins no unit template, role, or repo artifact mentions.

Two rules this module follows, both learned from the incident it exists for:

* **Never fabricate a reassuring value.** A unit that cannot be read emits no
  sample rather than a `0` reclaim count (which reads as "healthy") or a `-1`
  limit (which reads as "unlimited"). Absence is visible in a query; a wrong
  number is not.
* **Never let the scrape die.** Everything is best-effort per unit, and read
  failures are themselves exported as a metric — monitoring for a silent failure
  must not fail silently.

Sampled at scrape time via a custom collector: there is no event to hook, the
kernel updates these files continuously, and a polling task would only add a
staleness window.
"""

from __future__ import annotations

import re
from pathlib import Path

from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# cgroup v2 mount point. Overridable so tests can point at a fixture tree.
DEFAULT_CGROUP_ROOT = Path("/sys/fs/cgroup")

# Where systemd writes property drop-ins that no repo artifact records.
# `systemctl set-property` uses the first; `--runtime` uses the second and is
# lost on reboot, which makes it *more* confusing rather than less (#13765).
SYSTEMD_CONTROL_ROOTS: tuple[Path, ...] = (
    Path("/etc/systemd/system.control"),
    Path("/run/systemd/system.control"),
    # Hand-written drop-ins are equally undeclared. Same tree systemd reads for
    # unit overrides, and equally absent from the ansible roles.
    Path("/etc/systemd/system"),
)

# Only a drop-in that actually sets a memory property counts. The directory is
# created for ANY property (CPUQuota, Restart, …), so keying on its existence
# alone made the alert text — "its effective memory limits are not in the unit
# template" — false whenever someone had set something unrelated.
_MEMORY_PROPERTY = re.compile(r"^\s*Memory[A-Za-z]*\s*=", re.MULTILINE)

# Prefix of the units this collector discovers. A static list could not cover
# instance units such as autobot-mcp-bridge@.service — the only unit in the tree
# carrying a repo-declared MemoryMax — and needed editing per new service.
UNIT_GLOB = "autobot-*.service"

# `max` in memory.high / memory.max means unlimited. Exported as -1 so a
# "limit is set" query is `>= 0`. An UNREADABLE file is NOT this — it emits no
# sample at all, because reporting "unlimited" for a file we could not read is
# the reassuring-wrong-answer failure this whole issue is about.
UNLIMITED = -1.0

_LIMIT_FILES = ("memory.high", "memory.max")


class _Unreadable:
    """Sentinel: the file exists in principle but could not be parsed."""


UNREADABLE = _Unreadable()


def _read_text(path: Path) -> str | None:
    """Read *path*, or None on any failure.

    ``UnicodeDecodeError`` is a ``ValueError``, not an ``OSError`` — catching
    only the latter let a single non-UTF-8 byte in one cgroup file propagate out
    of ``collect()`` and 500 the whole ``/metrics`` endpoint, taking every other
    metric with it.
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _read_limit(path: Path) -> float | _Unreadable:
    """Return bytes, ``UNLIMITED`` for the literal ``max``, or ``UNREADABLE``."""
    raw = _read_text(path)
    if raw is None:
        return UNREADABLE
    raw = raw.strip()
    if raw == "max":
        return UNLIMITED
    try:
        return float(int(raw))
    except ValueError:
        logger.warning("cgroup: %s holds %r, not an integer", path, raw[:40])
        return UNREADABLE


def read_memory_events(cgroup_dir: Path) -> dict[str, int] | None:
    """Parse `memory.events`, or None when it cannot be read.

    None rather than ``{}``: an empty dict would silently mean "no counters",
    and a unit with no `high` counter cannot trip ServiceMemoryThrottled — which
    would look exactly like a healthy unit.
    """
    raw = _read_text(cgroup_dir / "memory.events")
    if raw is None:
        return None

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


def has_out_of_band_limits(unit: str, control_roots: tuple[Path, ...] = SYSTEMD_CONTROL_ROOTS) -> bool:
    """True when a drop-in outside the repo sets a memory property on *unit*.

    Checks the persistent and `--runtime` set-property trees plus hand-written
    overrides, and requires an actual ``Memory*=`` assignment rather than merely
    the directory's existence.
    """
    for root in control_roots:
        drop_in = root / f"{unit}.d"
        try:
            confs = sorted(drop_in.glob("*.conf"))
        except OSError:
            continue
        for conf in confs:
            text = _read_text(conf)
            if text and _MEMORY_PROPERTY.search(text):
                return True
    return False


class CgroupMemoryCollector(Collector):
    """Export cgroup v2 memory pressure for the platform's systemd units.

    Units are DISCOVERED under the cgroup root rather than listed, so a service
    moved by `Slice=` is still found. That matters here specifically: `systemctl
    set-property <unit> Slice=…` is the same out-of-band mechanism this collector
    exists to detect, and a hardcoded `system.slice` path would have been
    defeated by it — silently.
    """

    def __init__(
        self,
        cgroup_root: Path = DEFAULT_CGROUP_ROOT,
        control_roots: tuple[Path, ...] = SYSTEMD_CONTROL_ROOTS,
        unit_glob: str = UNIT_GLOB,
    ) -> None:
        self.cgroup_root = cgroup_root
        self.control_roots = control_roots
        self.unit_glob = unit_glob

    def discover_units(self) -> dict[str, Path]:
        """Map unit name -> cgroup dir, wherever in the slice tree it sits."""
        found: dict[str, Path] = {}
        try:
            for path in sorted(self.cgroup_root.rglob(self.unit_glob)):
                if path.is_dir():
                    found.setdefault(path.name, path)
        except OSError as exc:
            logger.warning("cgroup: cannot walk %s: %s", self.cgroup_root, exc)
        return found

    def _families(self) -> dict[str, GaugeMetricFamily]:
        return {
            "events": GaugeMetricFamily(
                "autobot_cgroup_memory_events",
                "cgroup v2 memory.events counters; `high` is the reclaim counter that "
                "rises while a cgroup is throttled but still reports active (#13765). "
                "Monotonic despite the gauge type — see the module docstring.",
                labels=["unit", "event"],
            ),
            "current": GaugeMetricFamily(
                "autobot_cgroup_memory_current_bytes",
                "Current cgroup memory usage in bytes",
                labels=["unit"],
            ),
            "high": GaugeMetricFamily(
                "autobot_cgroup_memory_high_bytes",
                f"MemoryHigh throttling watermark in bytes; {UNLIMITED:.0f} when unlimited. "
                "Absent when the file could not be read — never guessed.",
                labels=["unit"],
            ),
            "max": GaugeMetricFamily(
                "autobot_cgroup_memory_max_bytes",
                f"MemoryMax hard limit in bytes; {UNLIMITED:.0f} when unlimited",
                labels=["unit"],
            ),
            "out_of_band": GaugeMetricFamily(
                "autobot_cgroup_memory_limits_out_of_band",
                "1 when a drop-in outside the repo sets a memory property on this unit, "
                "i.e. limits no artifact records and a fresh install would not reproduce",
                labels=["unit"],
            ),
            "errors": GaugeMetricFamily(
                "autobot_cgroup_memory_read_errors",
                "1 when a cgroup file for this unit could not be read. Exported so the "
                "monitoring for a silent failure cannot itself fail silently (#13765).",
                labels=["unit", "file"],
            ),
        }

    def _collect_unit(self, unit: str, unit_dir: Path, fam: dict[str, GaugeMetricFamily]) -> None:
        events = read_memory_events(unit_dir)
        if events is None:
            fam["errors"].add_metric([unit, "memory.events"], 1.0)
        else:
            for key, value in events.items():
                fam["events"].add_metric([unit, key], value)

        current = _read_limit(unit_dir / "memory.current")
        if isinstance(current, _Unreadable):
            fam["errors"].add_metric([unit, "memory.current"], 1.0)
        else:
            fam["current"].add_metric([unit], current)

        for filename in _LIMIT_FILES:
            value = _read_limit(unit_dir / filename)
            if isinstance(value, _Unreadable):
                # No sample. A -1 here would read as "unlimited" and silently
                # drop the unit out of the headroom rule (#13765 review).
                fam["errors"].add_metric([unit, filename], 1.0)
                continue
            fam[filename.split(".")[1]].add_metric([unit], value)

        fam["out_of_band"].add_metric([unit], 1.0 if has_out_of_band_limits(unit, self.control_roots) else 0.0)

    def describe(self):
        """Declare the families without touching the filesystem.

        Without this, `register()` records no names for the collector, so these
        series are invisible to a name-restricted scrape (`?name[]=`) and get no
        duplicate-registration checking.
        """
        return list(self._families().values())

    def collect(self):
        fam = self._families()
        for unit, unit_dir in self.discover_units().items():
            try:
                self._collect_unit(unit, unit_dir, fam)
            except Exception as exc:  # noqa: BLE001 - one bad unit must not end the scrape
                logger.warning("cgroup: collecting %s failed: %s", unit, exc)
                fam["errors"].add_metric([unit, "collect"], 1.0)
        yield from fam.values()


__all__ = [
    "CgroupMemoryCollector",
    "read_memory_events",
    "has_out_of_band_limits",
    "DEFAULT_CGROUP_ROOT",
    "SYSTEMD_CONTROL_ROOTS",
    "UNIT_GLOB",
    "UNLIMITED",
]
