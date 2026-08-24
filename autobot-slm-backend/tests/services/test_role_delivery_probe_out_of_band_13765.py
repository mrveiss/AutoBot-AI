# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Out-of-band memory overrides are a host-differs-from-repo condition (#13765).

`autobot-backend` ran for months under `MemoryHigh=8G` / `MemoryMax=12G` applied
by hand with `systemctl set-property`, which writes into
`/etc/systemd/system.control/`. Nothing in the unit template, the role or the
repo mentioned those values, a fresh install of the same commit got none, and
the state they produced — throttled, `STAT=D`, `/health` timing out, systemd
`active` — sent a full diagnostic cycle toward application code.

#13765's acceptance list asks for exactly this: the `system.control/` tree added
to the role-delivery probe, because a service running under limits its unit does
not declare is the condition that probe exists to catch.

Loaded past the suite's session-global ``services`` stub the same way as
``test_role_delivery_probe_12959.py``; without that every assertion here would
pass vacuously against MagicMock attributes.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent
_METRICS_DIR = _REPO_ROOT / "autobot_shared" / "monitoring" / "metrics"
_CGROUP_MEMORY = "autobot_shared.monitoring.metrics.cgroup_memory"


def _load(module_name: str, alias: str):
    saved = sys.modules.get("autobot_shared.logging_manager")
    sys.modules["autobot_shared.logging_manager"] = MagicMock()
    try:
        spec = importlib.util.spec_from_file_location(alias, _BACKEND_ROOT / "services" / f"{module_name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[alias] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved is None:
            sys.modules.pop("autobot_shared.logging_manager", None)
        else:
            sys.modules["autobot_shared.logging_manager"] = saved


_probe = _load("role_delivery_probe", "_rdp_13765")


@pytest.fixture(autouse=True)
def _resolvable_cgroup_memory():
    """Guarantee the collector's predicate resolves, whatever else leaked.

    `probe_out_of_band_limits` imports `has_out_of_band_limits` from the metrics
    collector at call time, and reports "could not look" when that import fails
    — correct behaviour in production, and exactly what happened here: several
    suite files replace `sys.modules["autobot_shared.monitoring"]` (and, when an
    `exec_module` raises before their restore block, `sys.modules["autobot_
    shared"]` itself) at MODULE scope with no teardown, so a stub survives for
    the rest of the session. Under xdist the victim is whichever worker drew the
    leaker, which is why this reddened one shard and not the other eleven.

    Every negative assertion in this file would pass against that stub — an
    unreadable-tree case and a scan-did-not-run case both expect an empty list —
    so without this the suite would have gone green for the wrong reason. Same
    load-past-the-stub technique `_load` above uses for `services/*`, one package
    level deeper.

    Restores sys.modules exactly, including deleting keys that were absent, so
    the repo-wide leak guard (#13337) sees a zero delta and this fixture does not
    become the next file in the paragraph above.
    """
    names = (_CGROUP_MEMORY, "autobot_shared.monitoring.metrics")
    saved = {name: sys.modules.get(name) for name in names}
    try:
        importlib.import_module(_CGROUP_MEMORY)
    except Exception:
        # Rebuild only what is missing: a real path-carrying package entry, then
        # the module itself loaded from disk. Deliberately does NOT execute
        # `metrics/__init__.py`, which would drag in every other collector.
        pkg = types.ModuleType("autobot_shared.monitoring.metrics")
        pkg.__path__ = [str(_METRICS_DIR)]
        sys.modules["autobot_shared.monitoring.metrics"] = pkg
        spec = importlib.util.spec_from_file_location(_CGROUP_MEMORY, _METRICS_DIR / "cgroup_memory.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_CGROUP_MEMORY] = module
        spec.loader.exec_module(module)
    yield
    for name, previous in saved.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


probe_out_of_band_limits = _probe.probe_out_of_band_limits
probe_role_delivery = _probe.probe_role_delivery
RoleInvariant = _probe.RoleInvariant
CONTAINS = _probe.CONTAINS

# The values the incident host actually carried.
_INCIDENT_DROP_IN = "MemoryHigh=8589934592\nMemoryMax=12884901888\n"


def _control_root(tmp_path: Path, unit: str = "autobot-backend.service", body: str = _INCIDENT_DROP_IN) -> Path:
    root = tmp_path / "system.control"
    drop_in = root / f"{unit}.d"
    drop_in.mkdir(parents=True)
    (drop_in / "50-MemoryHigh.conf").write_text(body, encoding="utf-8")
    return root


def test_the_predicate_under_test_actually_exists() -> None:
    """Assert the target before asserting about it.

    Every negative case below would pass against a probe that had lost the
    check entirely — an empty ``out_of_band`` list reads exactly like "nothing
    found". Pin the mechanism first, and pin that it is the collector's
    definition rather than a second one that can drift from the metric.
    """
    from autobot_shared.monitoring.metrics.cgroup_memory import has_out_of_band_limits

    assert callable(has_out_of_band_limits)
    source = (_BACKEND_ROOT / "services" / "role_delivery_probe.py").read_text(encoding="utf-8")
    assert "has_out_of_band_limits" in source, "the probe must reuse the collector's predicate, not reimplement it"


def test_the_incident_drop_in_is_reported(tmp_path: Path) -> None:
    """The literal state that ran undetected for months."""
    units, observed = probe_out_of_band_limits((_control_root(tmp_path),))

    assert observed
    assert units == ["autobot-backend.service"]


def test_every_service_is_covered_not_just_the_backend(tmp_path: Path) -> None:
    """#13765: `paperclip.service.d` was found alongside the backend's.

    The scan walks the tree instead of consulting a list of units, so a service
    nobody thought to enumerate is still covered.
    """
    root = _control_root(tmp_path, unit="paperclip.service")
    (root / "some-other.service.d").mkdir()
    (root / "some-other.service.d" / "override.conf").write_text("MemoryMax=4G\n", encoding="utf-8")

    units, observed = probe_out_of_band_limits((root,))

    assert observed
    assert units == ["paperclip.service", "some-other.service"]


def test_a_drop_in_that_sets_no_memory_property_is_not_a_finding(tmp_path: Path) -> None:
    """The directory exists for ANY property — CPUQuota, Restart, Slice.

    Keying on its existence would make the report's own words ("its effective
    memory limits are not in the unit template") false, and a permanent false
    warning is the failure this issue is about.
    """
    root = tmp_path / "system.control"
    (root / "autobot-celery.service.d").mkdir(parents=True)
    (root / "autobot-celery.service.d" / "50-CPUQuota.conf").write_text("CPUQuota=50%\n", encoding="utf-8")

    units, observed = probe_out_of_band_limits((root,))

    assert observed
    assert units == []


def test_an_absent_control_tree_is_clean_and_observed(tmp_path: Path) -> None:
    """`set-property` creates the tree on first use, so absence is a real answer.

    Distinct from "could not look": this must report observed, or a host that
    has simply never had an override applied would permanently read as
    unverifiable and train operators to ignore the field.
    """
    units, observed = probe_out_of_band_limits((tmp_path / "never-created",))

    assert units == []
    assert observed is True


def test_an_unreadable_tree_is_not_reported_as_clean(tmp_path: Path) -> None:
    """An empty result must not read as a clean result.

    A root that exists but cannot be listed yields the same empty list as a host
    with no overrides. The flag is what separates them, and it is the reason the
    caller can tell "nothing found" from "did not look".
    """
    root = tmp_path / "system.control"
    root.mkdir()
    root.chmod(0o000)
    try:
        units, observed = probe_out_of_band_limits((root,))
    finally:
        root.chmod(0o755)

    if units == [] and observed:
        pytest.skip("running as a user that can read a 0o000 directory (root); the flag cannot be exercised")
    assert units == []
    assert observed is False


def test_a_finding_degrades_the_verdict_and_names_the_unit(tmp_path: Path) -> None:
    """The probe feeds `self_update_incomplete`, so it has to actually degrade."""
    verdict = probe_role_delivery(checks=[], control_roots=(_control_root(tmp_path),))

    assert verdict.degraded
    assert verdict.out_of_band == ["autobot-backend.service"]
    assert "autobot-backend.service" in (verdict.reason or "")
    assert "#13765" in (verdict.reason or "")


def test_an_unreadable_tree_degrades_the_VERDICT_not_just_the_tuple(tmp_path: Path) -> None:
    """The property, not the helper — review found `degraded` ignoring the flag.

    `probe_out_of_band_limits` distinguished "clean" from "could not look" all
    along, and `_describe` composed the explanatory sentence, but `degraded`
    read only `out_of_band`. So an unreadable control tree returned an empty
    list, a False flag, and `degraded is False` — and both consumers dropped the
    sentence unread, because `_merge_role_delivery` returns early on
    `not degraded` and the fleet-update stage gates its pass/fail on the same
    property. An update-all job reported the stage successful on a host whose
    scan had silently failed.

    Testing the tuple only, as this file previously did, could never catch that:
    the tuple was correct. Drive the property.
    """
    root = tmp_path / "system.control"
    root.mkdir()
    root.chmod(0o000)
    try:
        verdict = probe_role_delivery(checks=[], control_roots=(root,))
    finally:
        root.chmod(0o755)

    if verdict.out_of_band_observed:
        pytest.skip("running as a user that can read a 0o000 directory (root); the flag cannot be exercised")

    assert verdict.out_of_band == []
    assert verdict.out_of_band_observed is False
    assert verdict.degraded is True, "a scan that could not run must not read as a clean host"
    assert "could not be checked" in (verdict.reason or "")


def test_a_scan_that_was_not_requested_is_not_a_degradation(tmp_path: Path) -> None:
    """`None` and `False` must not collapse.

    `None` means the caller passed explicit checks and never asked for the
    scan; `False` means it was asked for and could not run. Only the second is
    a failure to observe, so `degraded` tests `is False` rather than falsiness —
    otherwise every unit test passing explicit checks would degrade.
    """
    artifact = tmp_path / "unit.service"
    artifact.write_text("Environment=MARKER=1\n", encoding="utf-8")
    inv = RoleInvariant(
        role="backend",
        issue="#12777",
        artifact=artifact,
        kind=CONTAINS,
        marker="MARKER",
        describes="artifact is missing the role-owned change",
    )

    verdict = probe_role_delivery(checks=[inv])

    assert verdict.out_of_band_observed is None
    assert verdict.degraded is False


def test_a_readable_empty_tree_is_still_not_degraded(tmp_path: Path) -> None:
    """The fix must not turn every ordinary host into a permanent alarm.

    Most hosts have never had `systemctl set-property` run, so the tree does not
    exist. That is an observation, and observing nothing is clean.
    """
    verdict = probe_role_delivery(checks=[], control_roots=(tmp_path / "never-created",))

    assert verdict.out_of_band_observed is True
    assert verdict.degraded is False


def test_out_of_band_does_not_disturb_the_role_invariant_counters(tmp_path: Path) -> None:
    """`checked`/`skipped` count role-owned invariants and must keep doing so.

    Folding a fourth question into those counters would silently shift every
    existing count assertion in test_role_delivery_probe_12959.py by one.
    """
    artifact = tmp_path / "unit.service"
    artifact.write_text("Environment=MARKER=1\n", encoding="utf-8")
    inv = RoleInvariant(
        role="backend",
        issue="#12777",
        artifact=artifact,
        kind=CONTAINS,
        marker="MARKER",
        describes="artifact is missing the role-owned change",
    )

    verdict = probe_role_delivery(checks=[inv], control_roots=(_control_root(tmp_path),))

    assert verdict.checked == 1
    assert verdict.skipped == 0
    assert verdict.out_of_band == ["autobot-backend.service"]


def test_explicit_checks_alone_never_touch_the_real_host_tree(tmp_path: Path) -> None:
    """A unit test's verdict must not depend on the machine running it.

    The self-hosted runner IS the host whose out-of-band drop-in this issue was
    filed about, so an unconditional scan would have reddened unrelated
    assertions on one runner and passed on another.
    """
    artifact = tmp_path / "unit.service"
    artifact.write_text("Environment=MARKER=1\n", encoding="utf-8")
    inv = RoleInvariant(
        role="backend",
        issue="#12777",
        artifact=artifact,
        kind=CONTAINS,
        marker="MARKER",
        describes="artifact is missing the role-owned change",
    )

    verdict = probe_role_delivery(checks=[inv])

    assert verdict.out_of_band == []
    assert verdict.out_of_band_observed is None, "the scan must not have run at all"
    assert not verdict.degraded
