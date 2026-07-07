# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the proposal-only RemediationLoop (#11196).

Test plan:
  1. select_targets: <= MAX_BATCH, ranking preserved, fields mapped correctly.
  2. select_targets: empty report → [].
  3. record_delta: positive and negative health deltas computed correctly.
  4. record_delta: delta persisted via trend store (fake Redis zadd).
  5. record_delta: backend-down → returns delta, does NOT raise.
  6. snapshot: returns health fields from a stubbed report.
  7. Read-only contract: no dispatch/mutation entry point exists.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build lightweight stubs that match the real dataclass shapes.
# ---------------------------------------------------------------------------


def _make_ap(
    pattern_type: str = "god_class",
    severity: str = "high",
    file_path: str = "foo/bar.py",
    line_number: int = 10,
    suggestion: str = "Extract methods",
    runtime_risk: float = 0.3,
):
    """Return an AntiPatternInstance-shaped stub."""
    pt = SimpleNamespace(value=pattern_type)
    sv = SimpleNamespace(value=severity)
    return SimpleNamespace(
        pattern_type=pt,
        severity=sv,
        file_path=file_path,
        line_number=line_number,
        suggestion=suggestion,
        runtime_risk=runtime_risk,
    )


def _make_report(
    health_score: float = 75.0,
    critical_count: int = 1,
    high_count: int = 3,
    medium_count: int = 5,
    low_count: int = 2,
    anti_patterns=None,
):
    """Return an AntiPatternReport-shaped stub."""
    if anti_patterns is None:
        anti_patterns = []
    return SimpleNamespace(
        health_score=health_score,
        critical_count=critical_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        total_issues=len(anti_patterns),
        anti_patterns=anti_patterns,
    )


def _load_module():
    """Load remediation_loop from worktree-relative path (side-steps heavy dep chain)."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "remediation_loop_test_module",
        "autobot-backend/code_analysis/src/remediation_loop.py",
    )
    mod = importlib.util.module_from_spec(spec)

    # Stub autobot_shared sub-imports that the module references at load time.
    _stub_shared(sys)

    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        pytest.skip(f"remediation_loop dep chain unavailable: {exc}")

    return mod


def _stub_shared(sys_mod):
    """Insert lightweight stubs for autobot_shared so the module loads cleanly."""
    import types

    for name in [
        "autobot_shared",
        "autobot_shared.logging_manager",
        "autobot_shared.time_utils",
    ]:
        if name not in sys_mod.modules:
            sys_mod.modules[name] = types.ModuleType(name)

    lm = sys_mod.modules["autobot_shared.logging_manager"]
    if not hasattr(lm, "get_logger"):
        lm.get_logger = lambda _: MagicMock()

    tu = sys_mod.modules["autobot_shared.time_utils"]
    if not hasattr(tu, "now_utc"):
        from datetime import datetime, timezone

        tu.now_utc = lambda: datetime.now(timezone.utc)
    if not hasattr(tu, "utc_timestamp"):
        from datetime import datetime, timezone

        tu.utc_timestamp = lambda: datetime.now(timezone.utc).isoformat()

    # Keep autobot_shared package-level accessible
    shared = sys_mod.modules["autobot_shared"]
    shared.logging_manager = sys_mod.modules["autobot_shared.logging_manager"]
    shared.time_utils = sys_mod.modules["autobot_shared.time_utils"]


# ---------------------------------------------------------------------------
# 1. select_targets: <= MAX_BATCH, ranking preserved, fields correct.
# ---------------------------------------------------------------------------


class TestSelectTargets:
    def setup_method(self):
        self.mod = _load_module()
        self.loop = self.mod.RemediationLoop()

    def _patterns(self, count: int) -> list:
        return [
            _make_ap(
                pattern_type=f"pat_{i}",
                severity="high",
                file_path=f"file_{i}.py",
                line_number=i * 10,
                runtime_risk=float(i) / 10,
                suggestion=f"Fix {i}",
            )
            for i in range(count)
        ]

    def test_returns_at_most_max_batch(self):
        patterns = self._patterns(20)
        report = _make_report(anti_patterns=patterns)
        targets = self.loop.select_targets(report)
        assert len(targets) <= self.mod.REMEDIATION_MAX_BATCH

    def test_preserves_ranking_order(self):
        patterns = self._patterns(10)
        report = _make_report(anti_patterns=patterns)
        targets = self.loop.select_targets(report)
        for i, t in enumerate(targets):
            assert t["file"] == f"file_{i}.py", "Ranking order must not be altered"

    def test_maps_fields_correctly(self):
        ap = _make_ap(
            pattern_type="god_class",
            severity="critical",
            file_path="src/big.py",
            line_number=42,
            suggestion="Extract into smaller classes",
            runtime_risk=0.75,
        )
        report = _make_report(anti_patterns=[ap])
        targets = self.loop.select_targets(report, n=1)
        assert len(targets) == 1
        t = targets[0]
        assert t["file"] == "src/big.py"
        assert t["line"] == 42
        assert t["pattern_type"] == "god_class"
        assert t["severity"] == "critical"
        assert t["runtime_risk"] == 0.75
        assert t["suggestion"] == "Extract into smaller classes"

    def test_empty_report_returns_empty_list(self):
        report = _make_report(anti_patterns=[])
        assert self.loop.select_targets(report) == []

    def test_n_override_capped_to_max_batch(self):
        patterns = self._patterns(20)
        report = _make_report(anti_patterns=patterns)
        # n > MAX_BATCH must still be capped
        targets = self.loop.select_targets(report, n=self.mod.REMEDIATION_MAX_BATCH + 100)
        assert len(targets) == self.mod.REMEDIATION_MAX_BATCH

    def test_n_override_smaller_than_max_batch(self):
        patterns = self._patterns(10)
        report = _make_report(anti_patterns=patterns)
        targets = self.loop.select_targets(report, n=2)
        assert len(targets) == 2


# ---------------------------------------------------------------------------
# 2. record_delta: computes positive and negative deltas correctly.
# ---------------------------------------------------------------------------


class TestRecordDeltaComputation:
    def setup_method(self):
        self.mod = _load_module()
        self.loop = self.mod.RemediationLoop()

    def _run(self, before, after):
        import asyncio

        async def _go():
            with patch.object(self.mod, "_persist_delta", new=AsyncMock()):
                return await self.loop.record_delta(before, after)

        return asyncio.get_event_loop().run_until_complete(_go())

    def test_positive_health_delta(self):
        before = {"health_score": 60.0, "total_findings": 20}
        after = {"health_score": 75.0, "total_findings": 10}
        delta = self._run(before, after)
        assert abs(delta["health_delta"] - 15.0) < 1e-9
        assert delta["findings_delta"] == -10

    def test_negative_health_delta(self):
        before = {"health_score": 80.0, "total_findings": 5}
        after = {"health_score": 70.0, "total_findings": 8}
        delta = self._run(before, after)
        assert abs(delta["health_delta"] - (-10.0)) < 1e-9
        assert delta["findings_delta"] == 3

    def test_zero_delta(self):
        snap = {"health_score": 55.0, "total_findings": 12}
        delta = self._run(snap, snap)
        assert delta["health_delta"] == 0.0
        assert delta["findings_delta"] == 0

    def test_source_marker(self):
        before = {"health_score": 50.0, "total_findings": 0}
        after = {"health_score": 50.0, "total_findings": 0}
        delta = self._run(before, after)
        assert delta["source"] == "remediation_delta"


# ---------------------------------------------------------------------------
# 3. record_delta: persists a trend row via zadd.
# ---------------------------------------------------------------------------


class TestRecordDeltaPersistence:
    def setup_method(self):
        self.mod = _load_module()
        self.loop = self.mod.RemediationLoop()

    @pytest.mark.asyncio
    async def test_calls_zadd_on_redis(self):
        fake_redis = AsyncMock()
        fake_redis.zadd = AsyncMock(return_value=1)
        fake_redis.zremrangebyrank = AsyncMock(return_value=0)

        with patch("autobot_shared.redis_client.get_async_redis_client", new=AsyncMock(return_value=fake_redis)):
            # Patch the module-level import resolution
            with patch.dict(
                "sys.modules",
                {"autobot_shared.redis_client": MagicMock(get_async_redis_client=AsyncMock(return_value=fake_redis))},
            ):
                await self.mod._persist_delta({"health_delta": 10.0, "source": "remediation_delta"})

        # zadd must have been called with the delta history key
        assert fake_redis.zadd.called
        key_arg = fake_redis.zadd.call_args[0][0]
        assert key_arg == self.mod._DELTA_HISTORY_KEY

    @pytest.mark.asyncio
    async def test_persisted_payload_is_valid_json(self):
        captured = {}

        async def fake_zadd(key, mapping):
            captured.update({"key": key, "mapping": mapping})
            return 1

        fake_redis = AsyncMock()
        fake_redis.zadd = fake_zadd
        fake_redis.zremrangebyrank = AsyncMock(return_value=0)

        delta = {
            "health_delta": 5.0,
            "findings_delta": -3,
            "source": "remediation_delta",
            "timestamp": "2026-07-07T00:00:00+00:00",
        }
        with patch.dict(
            "sys.modules",
            {"autobot_shared.redis_client": MagicMock(get_async_redis_client=AsyncMock(return_value=fake_redis))},
        ):
            await self.mod._persist_delta(delta)

        assert captured, "zadd was never called"
        payload_str = list(captured["mapping"].keys())[0]
        parsed = json.loads(payload_str)
        assert parsed["source"] == "remediation_delta"


# ---------------------------------------------------------------------------
# 4. record_delta: backend-down → returns delta, does NOT raise.
# ---------------------------------------------------------------------------


class TestRecordDeltaBackendDown:
    def setup_method(self):
        self.mod = _load_module()
        self.loop = self.mod.RemediationLoop()

    @pytest.mark.asyncio
    async def test_no_raise_on_redis_failure(self):
        before = {"health_score": 70.0, "total_findings": 8}
        after = {"health_score": 78.0, "total_findings": 4}

        with patch.dict(
            "sys.modules",
            {
                "autobot_shared.redis_client": MagicMock(
                    get_async_redis_client=AsyncMock(side_effect=ConnectionError("redis down"))
                )
            },
        ):
            delta = await self.loop.record_delta(before, after)  # must not raise

        assert abs(delta["health_delta"] - 8.0) < 1e-9
        assert delta["source"] == "remediation_delta"


# ---------------------------------------------------------------------------
# 5. snapshot: returns health fields from a stubbed report.
# ---------------------------------------------------------------------------


class TestSnapshot:
    def setup_method(self):
        self.mod = _load_module()
        self.loop = self.mod.RemediationLoop()

    @pytest.mark.asyncio
    async def test_returns_health_score(self):
        report = _make_report(health_score=82.5, critical_count=0, high_count=2, medium_count=4, low_count=1)
        report.anti_patterns = []
        report.total_issues = 7

        snap = await self.loop.snapshot(report)
        assert snap["health_score"] == 82.5

    @pytest.mark.asyncio
    async def test_returns_severity_counts(self):
        report = _make_report(health_score=60.0, critical_count=3, high_count=5, medium_count=7, low_count=9)
        report.anti_patterns = []
        report.total_issues = 24

        snap = await self.loop.snapshot(report)
        assert snap["critical"] == 3
        assert snap["high"] == 5
        assert snap["medium"] == 7
        assert snap["low"] == 9

    @pytest.mark.asyncio
    async def test_returns_total_findings(self):
        aps = [_make_ap() for _ in range(6)]
        report = _make_report(anti_patterns=aps)
        snap = await self.loop.snapshot(report)
        assert snap["total_findings"] == 6

    @pytest.mark.asyncio
    async def test_returns_timestamp_string(self):
        report = _make_report()
        report.anti_patterns = []
        snap = await self.loop.snapshot(report)
        assert isinstance(snap["timestamp"], str)
        assert "T" in snap["timestamp"]  # ISO-8601 form


# ---------------------------------------------------------------------------
# 6. Read-only contract: no dispatch / code-mutation entry point exists.
# ---------------------------------------------------------------------------


class TestReadOnlyContract:
    """Assert that the module exposes NO code-mutation or dispatch entry point.

    Any function that writes source files, calls batch-implement, mutates code,
    or opens PRs would violate the STRICTLY READ-ONLY contract of this module.
    """

    def setup_method(self):
        self.mod = _load_module()

    def test_no_dispatch_function(self):
        forbidden_names = {
            "dispatch",
            "apply_fix",
            "write_file",
            "open_pr",
            "batch_implement",
            "execute_fix",
            "mutate",
            "patch_file",
            "auto_fix",
        }
        public_names = {name for name in dir(self.mod) if not name.startswith("__")}
        violations = forbidden_names & public_names
        assert not violations, f"Module exposes forbidden dispatch names: {violations}"

    def test_no_subprocess_import(self):
        """The module must not import subprocess (a proxy for file mutation)."""
        import inspect

        src = inspect.getsource(self.mod)
        assert "subprocess" not in src, "Module must not use subprocess"

    def test_no_open_write(self):
        """The module must not open any file in write mode."""
        import inspect

        src = inspect.getsource(self.mod)
        # open(..., "w") or open(..., mode="w") patterns
        assert "open(" not in src or '"w"' not in src, "Module must not write files via open()"

    def test_remediation_loop_class_has_only_safe_methods(self):
        """RemediationLoop must only expose snapshot, select_targets, record_delta."""
        loop_cls = self.mod.RemediationLoop
        public_methods = {
            name for name in dir(loop_cls) if not name.startswith("_") and callable(getattr(loop_cls, name))
        }
        allowed = {"snapshot", "select_targets", "record_delta"}
        extra = public_methods - allowed
        assert not extra, f"RemediationLoop exposes unexpected public methods: {extra}"
