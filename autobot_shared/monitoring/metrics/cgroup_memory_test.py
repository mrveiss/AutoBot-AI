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

import os
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
        """None, not {} — an empty dict reads as "no counters", and a unit with no
        `high` counter cannot trip the throttle alert, i.e. it looks healthy."""
        assert read_memory_events(tmp_path) is None

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
        c = CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=(tmp_path / "none",))

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

        c = CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=(tmp_path / "none",))
        events = _samples(c, "autobot_cgroup_memory_events")
        current = _samples(c, "autobot_cgroup_memory_current_bytes")

        assert current[(("unit", throttled),)] == current[(("unit", healthy),)], "usage must be indistinguishable"
        assert events[(("event", "high"), ("unit", throttled))] > 0
        assert events[(("event", "high"), ("unit", healthy))] == 0

    def test_unlimited_reports_minus_one_not_a_huge_number(self, tmp_path):
        """`max` must not read as a real limit, or headroom maths goes nonsense."""
        _make_cgroup(tmp_path, _UNIT, "high 0\n", 1024, "max", "max")
        c = CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=(tmp_path / "none",))

        assert _samples(c, "autobot_cgroup_memory_high_bytes")[(("unit", _UNIT),)] == -1
        assert _samples(c, "autobot_cgroup_memory_max_bytes")[(("unit", _UNIT),)] == -1

    def test_a_unit_that_is_not_running_here_is_silent(self, tmp_path):
        """Better no metric than a fabricated zero — a 0 reclaim count for an
        absent unit reads as 'healthy', which is a claim we cannot make."""
        c = CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=(tmp_path / "none",))
        assert _samples(c, "autobot_cgroup_memory_events") == {}
        assert _samples(c, "autobot_cgroup_memory_current_bytes") == {}

    def test_collect_survives_an_unreadable_cgroup(self, tmp_path):
        """A scrape must not raise because one file is missing."""
        d = tmp_path / "system.slice" / _UNIT
        d.mkdir(parents=True)  # directory exists, every file absent
        c = CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=(tmp_path / "none",))
        list(c.collect())


class TestOutOfBandLimits:
    """The second half of #13765: the limits were invisible for two months.

    `systemctl set-property` writes to /etc/systemd/system.control/, which no
    unit template, role, or repo artifact mentions — and which the update path
    never touches, so it survives deploys and outlives any fix made in the role.
    """

    def test_detects_a_set_property_dropin(self, tmp_path):
        d = tmp_path / f"{_UNIT}.d"
        d.mkdir(parents=True)
        (d / "50-MemoryHigh.conf").write_text("[Service]\nMemoryHigh=8589934592\n", encoding="utf-8")
        assert has_out_of_band_limits(_UNIT, control_roots=(tmp_path,)) is True

    def test_absent_tree_is_not_a_false_positive(self, tmp_path):
        assert has_out_of_band_limits(_UNIT, control_roots=(tmp_path / "nope",)) is False

    def test_a_dropin_for_another_unit_does_not_flag_this_one(self, tmp_path):
        """The issue notes paperclip.service.d exists on the same host — a
        per-unit check must not smear that across the fleet."""
        d = tmp_path / "paperclip.service.d"
        d.mkdir(parents=True)
        (d / "50-MemoryHigh.conf").write_text("[Service]\nMemoryHigh=1\n", encoding="utf-8")
        assert has_out_of_band_limits(_UNIT, control_roots=(tmp_path,)) is False

    def test_the_flag_is_exported_per_unit(self, tmp_path):
        control = tmp_path / "control"
        d = control / f"{_UNIT}.d"
        d.mkdir(parents=True)
        (d / "50-MemoryMax.conf").write_text("[Service]\nMemoryMax=12884901888\n", encoding="utf-8")
        other = "autobot-celery.service"
        _make_cgroup(tmp_path / "cg", _UNIT, "high 0\n", 1, "max", "max")
        _make_cgroup(tmp_path / "cg", other, "high 0\n", 1, "max", "max")

        c = CgroupMemoryCollector(cgroup_root=tmp_path / "cg", control_roots=(control,))
        flags = _samples(c, "autobot_cgroup_memory_limits_out_of_band")

        assert flags[(("unit", _UNIT),)] == 1.0
        assert flags[(("unit", other),)] == 0.0


class TestReadFailuresAreNeverReassuring:
    """#13765 review: three untested paths, each of which faked a healthy state.

    The module's rule is that a value we could not read is reported as absent,
    never as a comfortable number. `-1` on an unreadable limit meant "unlimited",
    which also silently dropped the unit out of the headroom rule — a wrong
    answer that looks like a working one.
    """

    def test_a_non_utf8_byte_is_handled_where_it_happens(self, tmp_path):
        """UnicodeDecodeError is a ValueError, not an OSError. Catching only the
        latter let one bad byte propagate out of collect() and 500 the whole
        /metrics endpoint, taking every other metric with it.

        Asserting merely that the scrape survives is NOT enough — the blanket
        `except Exception` around each unit would satisfy that on its own, so the
        first version of this test passed even with the fix reverted. What
        distinguishes the two is WHERE the failure is attributed and what
        survives it: handled at the read, the error is labelled with the file and
        the unit's other samples are still collected; handled by the outer net,
        the label is `collect` and everything else for that unit is lost.
        """
        d = tmp_path / "system.slice" / _UNIT
        d.mkdir(parents=True)
        (d / "memory.events").write_bytes(b"high 5\n\xff\xfe\n")
        (d / "memory.current").write_text("4096\n", encoding="utf-8")
        (d / "memory.high").write_text("8589934592\n", encoding="utf-8")

        c = CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=())
        errors = _samples(c, "autobot_cgroup_memory_read_errors")
        current = _samples(c, "autobot_cgroup_memory_current_bytes")
        highs = _samples(c, "autobot_cgroup_memory_high_bytes")

        assert errors.get((("file", "memory.events"), ("unit", _UNIT))) == 1.0, (
            "the bad read must be attributed to the file, not swallowed by the " "per-unit safety net"
        )
        assert (("file", "collect"), ("unit", _UNIT)) not in errors
        assert current[(("unit", _UNIT),)] == 4096, "sibling samples must survive"
        assert highs[(("unit", _UNIT),)] == 8589934592

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores chmod 000, so the file stays readable")
    def test_an_unreadable_limit_is_absent_not_unlimited(self, tmp_path):
        """-1 means 'no limit set'. Reporting it for a file we could not read is
        the reassuring-wrong-answer failure this whole issue is about."""
        d = _make_cgroup(tmp_path, _UNIT, "high 0\n", 1024, str(_INCIDENT_HIGH), "max")
        (d / "memory.high").chmod(0o000)
        try:
            c = CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=())
            highs = _samples(c, "autobot_cgroup_memory_high_bytes")
            errors = _samples(c, "autobot_cgroup_memory_read_errors")
        finally:
            (d / "memory.high").chmod(0o644)

        assert (("unit", _UNIT),) not in highs, "an unreadable limit must emit no sample"
        assert errors[(("file", "memory.high"), ("unit", _UNIT))] == 1.0

    def test_an_unreadable_events_file_is_reported_as_an_error(self, tmp_path):
        """Otherwise it is indistinguishable from a healthy unit: no `high`
        counter means ServiceMemoryThrottled can never fire for it."""
        d = _make_cgroup(tmp_path, _UNIT, "high 0\n", 1024, "max", "max")
        (d / "memory.events").unlink()

        errors = _samples(
            CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=()), "autobot_cgroup_memory_read_errors"
        )

        assert errors[(("file", "memory.events"), ("unit", _UNIT))] == 1.0

    def test_memory_current_read_failure_is_reported(self, tmp_path):
        """Usage is the context every other number is read against; losing it
        silently leaves the unit half-described."""
        d = _make_cgroup(tmp_path, _UNIT, "high 0\n", 1024, "max", "max")
        (d / "memory.current").unlink()

        errors = _samples(
            CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=()),
            "autobot_cgroup_memory_read_errors",
        )

        assert errors[(("file", "memory.current"), ("unit", _UNIT))] == 1.0

    def test_the_shallowest_path_wins_when_a_name_appears_twice(self, tmp_path):
        """Precedence is by DEPTH, not lexicographic order over the full path.

        Sorting strings put `/a.slice/deep/deep/deep/autobot-backend.service`
        ahead of `/system.slice/autobot-backend.service` — so a nested delegated
        cgroup in an alphabetically earlier slice silently became the source of
        truth for the unit, and the real one was never read.
        """
        _make_cgroup(tmp_path, _UNIT, "high 0\n", 1, "max", "max")
        deep = tmp_path / "a.slice" / "d1" / "d2" / _UNIT
        deep.mkdir(parents=True)
        (deep / "memory.events").write_text(_INCIDENT_EVENTS, encoding="utf-8")

        found = CgroupMemoryCollector(cgroup_root=tmp_path).discover_units()

        assert (
            found[_UNIT] == tmp_path / "system.slice" / _UNIT
        ), "the shallow, real cgroup must win over a deeply nested namesake"

    def test_a_unit_outside_system_slice_is_still_found(self, tmp_path):
        """`systemctl set-property <unit> Slice=…` is the SAME out-of-band
        mechanism this collector detects. A hardcoded system.slice path would be
        defeated by it, silently — the detector beaten by the thing it detects."""
        nested = tmp_path / "machine.slice" / "custom.slice" / _UNIT
        nested.mkdir(parents=True)
        (nested / "memory.events").write_text(_INCIDENT_EVENTS, encoding="utf-8")

        c = CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=())
        events = _samples(c, "autobot_cgroup_memory_events")

        assert events[(("event", "high"), ("unit", _UNIT))] == 21052

    def test_a_property_that_is_not_a_limit_does_not_flag_drift(self, tmp_path):
        """MemoryAccounting=yes is the single most likely drop-in an operator
        adds — it is what makes these very metrics exist — and
        MemoryDenyWriteExecute is already set by this repo's own unit templates.
        Flagging either would page about config drift on a unit under no limit
        at all, which is how an alert gets ignored."""
        d = tmp_path / f"{_UNIT}.d"
        d.mkdir(parents=True)
        (d / "50-accounting.conf").write_text(
            "[Service]\nMemoryAccounting=yes\nMemoryDenyWriteExecute=true\n", encoding="utf-8"
        )
        assert has_out_of_band_limits(_UNIT, control_roots=(tmp_path,)) is False

    def test_an_empty_assignment_is_a_reset_not_a_limit(self, tmp_path):
        """`MemoryMax=` resets the property to its default — explicitly NO
        limit, the opposite of drift."""
        d = tmp_path / f"{_UNIT}.d"
        d.mkdir(parents=True)
        (d / "50-reset.conf").write_text("[Service]\nMemoryMax=\n", encoding="utf-8")
        assert has_out_of_band_limits(_UNIT, control_roots=(tmp_path,)) is False

    def test_an_ansible_rendered_drop_in_is_not_out_of_band(self, tmp_path):
        """The redis role renders MemoryLimit= into
        /etc/systemd/system/redis-stack-server.service.d/override.conf. Scanning
        that tree made ServiceMemoryLimitsOutOfBand fire permanently on every
        host, for a limit that IS in a role, advising removal of an
        ansible-managed file. Only the set-property trees are in scope."""
        from autobot_shared.monitoring.metrics.cgroup_memory import SYSTEMD_CONTROL_ROOTS

        assert Path("/etc/systemd/system") not in SYSTEMD_CONTROL_ROOTS
        assert all(root.name == "system.control" for root in SYSTEMD_CONTROL_ROOTS)


class TestAlertRules:
    """Structure only. BEHAVIOUR lives in cgroup-memory.promtool-test.yml.

    The previous version asserted substrings of the expr strings — that
    `"autobot_cgroup_memory_high_rate"` appeared, and that
    `"autobot_cgroup_memory_current_bytes >"` did not. Both passed while the
    headroom alert was structurally dead, because a substring says nothing about
    what the PromQL evaluates to. What is kept here is only what promtool cannot
    express.
    """

    @pytest.fixture
    def monitoring_dir(self):
        return Path(__file__).resolve().parents[3] / "autobot-monitoring"

    @pytest.fixture
    def rules(self, monitoring_dir):
        yaml = pytest.importorskip("yaml")
        return yaml.safe_load((monitoring_dir / "alerts-cgroup-memory.yml").read_text(encoding="utf-8"))

    def test_every_alert_is_exercised_by_the_promtool_suite(self, rules, monitoring_dir):
        """An alert with no rule test is exactly how the dead one shipped."""
        yaml = pytest.importorskip("yaml")
        suite = yaml.safe_load((monitoring_dir / "cgroup-memory.promtool-test.yml").read_text(encoding="utf-8"))

        declared = {r["alert"] for g in rules["groups"] for r in g["rules"] if "alert" in r}

        # Non-empty exp_alerts only. Keying on alertname alone accepted a suite
        # of `exp_alerts: []` entries — asserting each alert NEVER fires — which
        # the original dead headroom rule would have sailed through, since the
        # healthy/unlimited case already lists it with an empty expectation.
        proven_to_fire = {
            case["alertname"] for t in suite["tests"] for case in t.get("alert_rule_test", []) if case.get("exp_alerts")
        }

        assert declared <= proven_to_fire, (
            "alerts with no promtool case that actually FIRES: " f"{sorted(declared - proven_to_fire)}"
        )

    def test_the_out_of_band_alert_is_not_critical(self, rules):
        alerts = {r["alert"]: r for g in rules["groups"] for r in g["rules"] if "alert" in r}
        assert alerts["ServiceMemoryLimitsOutOfBand"]["labels"]["severity"] == "warning", (
            "an out-of-band limit is config drift, not an outage — someone set it "
            "deliberately, and paging on it would train people to ignore it"
        )

    def test_recording_and_alerting_rules_share_one_group(self, rules):
        """Rules evaluate in order within a group but independently across
        groups, so a split lets an alert read a stale recorded series."""
        with_records = {g["name"] for g in rules["groups"] if any("record" in r for r in g["rules"])}
        with_alerts = {g["name"] for g in rules["groups"] if any("alert" in r for r in g["rules"])}
        assert with_records == with_alerts


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

    def test_real_samples_render_through_the_manager(self, tmp_path):
        """`# HELP` alone proves nothing — prometheus_client emits it for EMPTY
        families, so the previous version of this test passed with zero samples
        and merely duplicated the registration check."""
        from autobot_shared.monitoring.prometheus_metrics import PrometheusMetricsManager

        _make_cgroup(tmp_path, _UNIT, _INCIDENT_EVENTS, _INCIDENT_CURRENT, str(_INCIDENT_HIGH), str(_INCIDENT_MAX))
        manager = PrometheusMetricsManager()
        manager._cgroup_memory.cgroup_root = tmp_path
        manager._cgroup_memory.control_roots = (tmp_path / "none",)

        text = manager.get_metrics().decode()

        assert 'autobot_cgroup_memory_events{event="high",unit="autobot-backend.service"} 21052' in text

    def test_describe_registers_the_family_names(self, tmp_path):
        """Without describe(), CollectorRegistry(auto_describe=False) records no
        names for this collector — so it is invisible to a name-restricted
        scrape and gets no duplicate-name checking. Deleting the method left the
        whole suite green, which made it one refactor from silently reverting."""
        from prometheus_client import CollectorRegistry, generate_latest

        from autobot_shared.monitoring.metrics.cgroup_memory import CgroupMemoryCollector

        _make_cgroup(tmp_path, _UNIT, _INCIDENT_EVENTS, _INCIDENT_CURRENT, str(_INCIDENT_HIGH), "max")
        registry = CollectorRegistry()
        collector = CgroupMemoryCollector(cgroup_root=tmp_path, control_roots=())
        registry.register(collector)

        # restricted_registry() is the public surface that DEPENDS on describe():
        # without it the registry records no names for this collector, so a
        # `?name[]=` scrape renders nothing at all. Asserted with real samples —
        # an empty family renders empty either way and would prove nothing.
        rendered = generate_latest(registry.restricted_registry(["autobot_cgroup_memory_events"])).decode()
        assert "autobot_cgroup_memory_events" in rendered
        assert "autobot_cgroup_memory_current_bytes" not in rendered, "restriction must exclude the rest"

        assert set(registry._collector_to_names[collector]) == {
            "autobot_cgroup_memory_events",
            "autobot_cgroup_memory_current_bytes",
            "autobot_cgroup_memory_high_bytes",
            "autobot_cgroup_memory_max_bytes",
            "autobot_cgroup_memory_limits_out_of_band",
            "autobot_cgroup_memory_read_errors",
        }

    def test_the_default_unit_glob_would_find_the_incident_unit(self, tmp_path):
        """Discovery, not a hardcoded list: a static list could not cover
        instance units (autobot-mcp-bridge@.service is the only unit in the tree
        with a repo-declared MemoryMax) and needed editing per new service."""
        _make_cgroup(tmp_path, "autobot-backend.service", "high 1\n", 1, "max", "max")
        _make_cgroup(tmp_path, "autobot-mcp-bridge@0.service", "high 0\n", 1, "max", "max")
        _make_cgroup(tmp_path, "unrelated-thing.service", "high 0\n", 1, "max", "max")

        _make_cgroup(tmp_path, "slm-agent.service", "high 0\n", 1, "max", "max")

        found = CgroupMemoryCollector(cgroup_root=tmp_path).discover_units()

        assert "autobot-backend.service" in found
        assert "autobot-mcp-bridge@0.service" in found, "instance units must be discovered"
        assert "slm-agent.service" in found, (
            "slm-agent declares MemoryHigh=200M — the only unit besides the backend "
            "that can enter the throttled-but-active state, and an autobot-* glob "
            "alone silently excluded it"
        )
        assert "unrelated-thing.service" not in found
