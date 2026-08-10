# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""cgroup memory pressure metrics (#13765).

The incident these exist for: autobot-backend pinned at an 8 GiB MemoryHigh
watermark, `memory.events high` at 21,052, STAT=D, /health timing out — and
`systemctl` reporting `active` the whole time. The tests below are written
against that exact shape, because the thing that makes it dangerous is that
every conventional signal looks fine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autobot_shared.monitoring.metrics.cgroup_memory import (
    CgroupMemoryCollector,
    has_out_of_band_limits,
    read_memory_events,
)

_UNIT = "autobot-backend.service"

# Verbatim shape of the incident, from the issue.
_INCIDENT_EVENTS = "low 0\nhigh 21052\nmax 0\noom 0\noom_kill 0\n"
_INCIDENT_CURRENT = 8589934592 - 1048576  # pinned just under the 8 GiB watermark
_INCIDENT_HIGH = 8589934592  # 8 GiB
_INCIDENT_MAX = 12884901888  # 12 GiB


def _make_cgroup(root: Path, unit: str, events: str, current: int, high: str, maximum: str) -> Path:
    d = root / "system.slice" / unit
    d.mkdir(parents=True)
    (d / "memory.events").write_text(events, encoding="utf-8")
    (d / "memory.current").write_text(f"{current}\n", encoding="utf-8")
    (d / "memory.high").write_text(f"{high}\n", encoding="utf-8")
    (d / "memory.max").write_text(f"{maximum}\n", encoding="utf-8")
    return d


def _samples(collector: CgroupMemoryCollector, name: str) -> dict[tuple, float]:
    out: dict[tuple, float] = {}
    for family in collector.collect():
        for sample in family.samples:
            if sample.name == name:
                out[tuple(sorted(sample.labels.items()))] = sample.value
    return out


class TestReadMemoryEvents:
    def test_parses_the_incident_counters(self, tmp_path):
        d = _make_cgroup(tmp_path, _UNIT, _INCIDENT_EVENTS, _INCIDENT_CURRENT, str(_INCIDENT_HIGH), str(_INCIDENT_MAX))
        assert read_memory_events(d)["high"] == 21052

    def test_absent_file_is_empty_not_an_error(self, tmp_path):
        """A metrics read must never break the scrape on a non-cgroup-v2 host."""
        assert read_memory_events(tmp_path) == {}

    def test_unknown_keys_survive(self, tmp_path):
        """A future kernel counter should be visible without a code change."""
        d = tmp_path / "cg"
        d.mkdir()
        (d / "memory.events").write_text("high 5\nsome_future_counter 9\n", encoding="utf-8")
        assert read_memory_events(d)["some_future_counter"] == 9

    def test_malformed_lines_are_skipped_not_fatal(self, tmp_path):
        d = tmp_path / "cg"
        d.mkdir()
        (d / "memory.events").write_text("high 7\ngarbage\nbad value\n", encoding="utf-8")
        assert read_memory_events(d) == {"high": 7}


class TestCollector:
    def test_exports_the_reclaim_counter(self, tmp_path):
        """The whole point: `high` is the only signal that separates a throttled
        service from a healthy one."""
        _make_cgroup(tmp_path, _UNIT, _INCIDENT_EVENTS, _INCIDENT_CURRENT, str(_INCIDENT_HIGH), str(_INCIDENT_MAX))
        c = CgroupMemoryCollector([_UNIT], cgroup_root=tmp_path, control_root=tmp_path / "none")

        events = _samples(c, "autobot_cgroup_memory_events")
        assert events[(("event", "high"), ("unit", _UNIT))] == 21052

    def test_the_throttled_state_is_distinguishable_from_healthy(self, tmp_path):
        """Two cgroups with near-identical usage — one throttled, one not.

        This is the assertion that matters. Usage, unit state and health all look
        the same across these two; only the reclaim counter differs, so a metric
        set that could not tell them apart would be worthless no matter how many
        gauges it exported.
        """
        throttled = "autobot-backend.service"
        healthy = "autobot-celery.service"
        _make_cgroup(tmp_path, throttled, _INCIDENT_EVENTS, _INCIDENT_CURRENT, str(_INCIDENT_HIGH), str(_INCIDENT_MAX))
        _make_cgroup(tmp_path, healthy, "low 0\nhigh 0\nmax 0\n", _INCIDENT_CURRENT, "max", "max")

        c = CgroupMemoryCollector([throttled, healthy], cgroup_root=tmp_path, control_root=tmp_path / "none")
        events = _samples(c, "autobot_cgroup_memory_events")
        current = _samples(c, "autobot_cgroup_memory_current_bytes")

        assert current[(("unit", throttled),)] == current[(("unit", healthy),)], "usage must be indistinguishable"
        assert events[(("event", "high"), ("unit", throttled))] > 0
        assert events[(("event", "high"), ("unit", healthy))] == 0

    def test_unlimited_reports_minus_one_not_a_huge_number(self, tmp_path):
        """`max` must not read as a real limit, or headroom maths goes nonsense."""
        _make_cgroup(tmp_path, _UNIT, "high 0\n", 1024, "max", "max")
        c = CgroupMemoryCollector([_UNIT], cgroup_root=tmp_path, control_root=tmp_path / "none")

        assert _samples(c, "autobot_cgroup_memory_high_bytes")[(("unit", _UNIT),)] == -1
        assert _samples(c, "autobot_cgroup_memory_max_bytes")[(("unit", _UNIT),)] == -1

    def test_a_unit_that_is_not_running_here_is_silent(self, tmp_path):
        """Better no metric than a fabricated zero — a 0 reclaim count for an
        absent unit reads as 'healthy', which is a claim we cannot make."""
        c = CgroupMemoryCollector(["not-deployed.service"], cgroup_root=tmp_path, control_root=tmp_path / "none")
        assert _samples(c, "autobot_cgroup_memory_events") == {}
        assert _samples(c, "autobot_cgroup_memory_current_bytes") == {}

    def test_collect_survives_an_unreadable_cgroup(self, tmp_path):
        """A scrape must not raise because one file is missing."""
        d = tmp_path / "system.slice" / _UNIT
        d.mkdir(parents=True)  # directory exists, every file absent
        c = CgroupMemoryCollector([_UNIT], cgroup_root=tmp_path, control_root=tmp_path / "none")
        list(c.collect())


class TestOutOfBandLimits:
    """The second half of #13765: the limits were invisible for two months.

    `systemctl set-property` writes to /etc/systemd/system.control/, which no
    unit template, role, or repo artifact mentions — and which the update path
    never touches, so it survives deploys and outlives any fix made in the role.
    """

    def test_detects_a_set_property_dropin(self, tmp_path):
        (tmp_path / f"{_UNIT}.d").mkdir(parents=True)
        assert has_out_of_band_limits(_UNIT, control_root=tmp_path) is True

    def test_absent_tree_is_not_a_false_positive(self, tmp_path):
        assert has_out_of_band_limits(_UNIT, control_root=tmp_path / "nope") is False

    def test_a_dropin_for_another_unit_does_not_flag_this_one(self, tmp_path):
        """The issue notes paperclip.service.d exists on the same host — a
        per-unit check must not smear that across the fleet."""
        (tmp_path / "paperclip.service.d").mkdir(parents=True)
        assert has_out_of_band_limits(_UNIT, control_root=tmp_path) is False

    def test_the_flag_is_exported_per_unit(self, tmp_path):
        control = tmp_path / "control"
        (control / f"{_UNIT}.d").mkdir(parents=True)
        other = "autobot-celery.service"
        _make_cgroup(tmp_path / "cg", _UNIT, "high 0\n", 1, "max", "max")
        _make_cgroup(tmp_path / "cg", other, "high 0\n", 1, "max", "max")

        c = CgroupMemoryCollector([_UNIT, other], cgroup_root=tmp_path / "cg", control_root=control)
        flags = _samples(c, "autobot_cgroup_memory_limits_out_of_band")

        assert flags[(("unit", _UNIT),)] == 1.0
        assert flags[(("unit", other),)] == 0.0


class TestAlertRules:
    """The rules must fire on the reclaim RATE, never on a usage threshold."""

    @pytest.fixture
    def rules(self):
        yaml = pytest.importorskip("yaml")
        path = Path(__file__).resolve().parents[3] / "autobot-monitoring" / "alerts-cgroup-memory.yml"
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_the_throttle_alert_fires_on_the_reclaim_counter(self, rules):
        alerts = {r["alert"]: r for g in rules["groups"] for r in g["rules"] if "alert" in r}
        expr = alerts["ServiceMemoryThrottled"]["expr"]
        assert "autobot_cgroup_memory_high_rate" in expr

    def test_no_alert_keys_off_absolute_memory_usage(self, rules):
        """A usage threshold cannot see this failure — the cgroup is *held* at
        its watermark, so 'high memory' is the normal state of a throttled
        service and of a healthy one near its cap alike."""
        for group in rules["groups"]:
            for rule in group["rules"]:
                if "alert" not in rule:
                    continue
                expr = rule["expr"]
                assert "autobot_cgroup_memory_current_bytes >" not in expr, (
                    f"{rule['alert']} thresholds on raw usage, which cannot "
                    "distinguish throttled from healthy (#13765)"
                )

    def test_the_out_of_band_alert_exists_and_is_not_critical(self, rules):
        alerts = {r["alert"]: r for g in rules["groups"] for r in g["rules"] if "alert" in r}
        rule = alerts["ServiceMemoryLimitsOutOfBand"]
        assert rule["labels"]["severity"] == "warning", (
            "an out-of-band limit is config drift, not an outage — someone set it "
            "deliberately and paging on it would train people to ignore it"
        )


class TestItIsActuallyWired:
    """#13765 would be pointless as an unregistered collector.

    This umbrella catalogues features that were built and never ran (#13685: two
    context layers that structurally could not render, so the A/B could never
    have won). A metric nobody scrapes is the same failure — worse here, because
    the whole point is to make an invisible state visible.
    """

    def test_the_collector_is_registered_on_the_real_manager(self):
        from autobot_shared.monitoring.prometheus_metrics import PrometheusMetricsManager

        manager = PrometheusMetricsManager()
        assert any(
            type(c).__name__ == "CgroupMemoryCollector" for c in manager.registry._collector_to_names
        ), "CgroupMemoryCollector is not registered — the metrics would never be scraped"

    def test_the_families_appear_in_scrape_output(self):
        """Registration alone is not enough; the families must render."""
        from autobot_shared.monitoring.prometheus_metrics import PrometheusMetricsManager

        text = PrometheusMetricsManager().get_metrics().decode()
        for family in (
            "autobot_cgroup_memory_events",
            "autobot_cgroup_memory_current_bytes",
            "autobot_cgroup_memory_limits_out_of_band",
        ):
            assert f"# HELP {family}" in text, f"{family} missing from /metrics"

    def test_the_watched_list_includes_the_unit_from_the_incident(self):
        from autobot_shared.monitoring.prometheus_metrics import THROTTLE_WATCHED_UNITS

        assert "autobot-backend.service" in THROTTLE_WATCHED_UNITS
