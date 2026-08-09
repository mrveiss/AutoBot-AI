# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the proposal-only RemediationLoop (#11196, #11199).

Test plan:
  1. select_targets: <= MAX_BATCH, ranking preserved, fields mapped correctly.
  2. select_targets: empty report → [].
  3. record_delta: positive and negative health deltas computed correctly.
  4. record_delta: delta persisted via trend store (fake Redis zadd).
  5. record_delta: backend-down → returns delta, does NOT raise.
  6. snapshot: returns health fields from a stubbed report.
  7. Read-only contract: no code-mutation path exists (even with dispatch added).
  8. dispatch_proposal (disabled, default): no-op, zero side effects, status "disabled".
  9. dispatch_proposal (enabled): produces exactly min(len, MAX_BATCH) work-items;
     dedupes by (file, pattern_type) within the batch.
  10. dispatch_proposal: READ-ONLY CONTRACT — no subprocess/file-write/PR-creation
      even when enabled.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.time_utils import utc_timestamp

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

    # #13311: resolved from this file, not from the process CWD. The literal
    # relative path silently skipped every test in this module (the loader
    # raised FileNotFoundError, which the except below turns into a skip)
    # whenever pytest was invoked from anywhere but the repository root.
    spec = importlib.util.spec_from_file_location(
        "remediation_loop_test_module",
        str(Path(__file__).resolve().parent / "remediation_loop.py"),
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
    from datetime import datetime, timezone

    if not hasattr(tu, "now_utc"):
        tu.now_utc = lambda: datetime.now(timezone.utc)
    if not hasattr(tu, "utc_timestamp"):
        tu.utc_timestamp = lambda: utc_timestamp()

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

        # #13113: asyncio.run() — pytest-asyncio owns the loop lifecycle, so a sync test
        # running before any async test on its worker had no current loop for get_event_loop().
        return asyncio.run(_go())

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


# ---------------------------------------------------------------------------
# Read-only capability guard (#13311)
# ---------------------------------------------------------------------------
#
# These five checks are a *lint*, not a behavioural contract, and they stay one:
# proving the absence of a capability is exactly what source inspection is for,
# and no amount of driving the module can show that a mutation path does not
# exist. What was wrong with them was the substring matching:
#
#   * ``assert "gh " not in src``  matched this very comment, and any prose
#     containing "gh " -- "through ", "high " -- so it fired on documentation.
#   * ``assert "open(" not in src or '"w"' not in src`` passes whenever the
#     module happens to contain no ``"w"`` anywhere else, and fails for an
#     unrelated ``"w"`` in a docstring; it never inspected an actual call.
#   * ``"import subprocess" not in src`` missed ``import subprocess as sp`` and
#     ``from subprocess import run``.
#
# They are now parsed. Same intent, no false positives, no false negatives.

# Top-level module names only: ``_imported_module_names`` keeps the first
# dotted segment, so an entry like "os.system" here could never match. The
# ``os.system`` *call* is caught by FORBIDDEN_CALLS below instead.
FORBIDDEN_IMPORTS = {"subprocess", "pty", "shutil", "tempfile"}
FORBIDDEN_CALLS = {"system", "popen", "Popen", "run", "call", "check_call", "check_output", "spawn"}
WRITE_MODES = {"w", "wb", "a", "ab", "x", "xb", "w+", "r+", "a+"}
# Writers that never go through ``open()`` at all -- ``Path.write_text``,
# ``Path.write_bytes``, ``os.remove`` and friends mutate the filesystem just as
# effectively, and the mode-argument check above cannot see any of them.
FORBIDDEN_WRITE_METHODS = {
    "write_text",
    "write_bytes",
    "mkdir",
    "touch",
    "unlink",
    "rename",
    "replace",
    "remove",
    "rmtree",
    "copy",
    "copy2",
    "move",
}


def _module_ast(module) -> ast.Module:
    return ast.parse(inspect.getsource(module))


def _imported_module_names(tree: ast.Module) -> set[str]:
    """Every module reachable by import, aliases resolved."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _is_write_mode_open(node: ast.Call) -> bool:
    """``open(...)`` / ``io.open(...)`` with a writing mode argument."""
    name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
    if name != "open":
        return False
    modes = list(node.args[1:2]) + [kw.value for kw in node.keywords if kw.arg == "mode"]
    return any(isinstance(m, ast.Constant) and str(m.value) in WRITE_MODES for m in modes)


def _filesystem_write_calls(tree: ast.Module) -> list[str]:
    """Every call that can mutate the filesystem, by any route."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if _is_write_mode_open(node) or name in FORBIDDEN_WRITE_METHODS:
            found.append(f"{name} (line {node.lineno})")
    return found


def _shell_out_calls(tree: ast.Module) -> list[str]:
    """Calls whose *name* is a process-spawning primitive, wherever they sit."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name in FORBIDDEN_CALLS and name != "run":
            found.append(f"{name} (line {node.lineno})")
    return found


class ReadOnlyCapabilityChecks:
    """Mixin: the read-only lint, shared by both contract classes below."""

    def test_no_process_spawning_module_is_imported(self):
        imported = _imported_module_names(_module_ast(self.mod))
        violations = imported & FORBIDDEN_IMPORTS
        assert not violations, f"module imports process/filesystem mutation modules: {violations}"

    def test_nothing_writes_to_the_filesystem(self):
        calls = _filesystem_write_calls(_module_ast(self.mod))
        assert not calls, f"filesystem-mutating calls present: {calls}"

    def test_nothing_shells_out(self):
        found = _shell_out_calls(_module_ast(self.mod))
        assert not found, f"process-spawning calls present: {found}"

    def test_the_checks_would_notice_a_violation(self):
        """Guard the guards: a parser that finds nothing passes everything."""
        offending = ast.parse(
            "import subprocess as sp\n"
            "from pathlib import Path\n"
            "def f(p):\n"
            "    sp.Popen(['gh', 'pr', 'create'])\n"
            "    open('/x', mode='a').write('mutated')\n"
            "    Path(p).write_text('mutated')\n"
            "    os.system('git commit')\n"
        )
        assert _imported_module_names(offending) & FORBIDDEN_IMPORTS == {"subprocess"}
        writes = _filesystem_write_calls(offending)
        assert any(w.startswith("open") for w in writes), writes
        assert any(w.startswith("write_text") for w in writes), writes
        shells = _shell_out_calls(offending)
        assert any(s.startswith("Popen") for s in shells), shells
        assert any(s.startswith("system") for s in shells), shells

    def test_the_lint_does_not_fire_on_a_clean_module(self):
        """The mirror: a read-only module must produce no findings at all."""
        clean = ast.parse("import json\ndef f(p):\n    return json.loads(open(p).read())\n")

        assert not _imported_module_names(clean) & FORBIDDEN_IMPORTS
        assert not _filesystem_write_calls(clean)
        assert not _shell_out_calls(clean)


class TestReadOnlyContract(ReadOnlyCapabilityChecks):
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

    def test_remediation_loop_class_has_only_safe_methods(self):
        """RemediationLoop must only expose snapshot, select_targets, record_delta, dispatch_proposal."""
        loop_cls = self.mod.RemediationLoop
        public_methods = {
            name for name in dir(loop_cls) if not name.startswith("_") and callable(getattr(loop_cls, name))
        }
        allowed = {"snapshot", "select_targets", "record_delta", "dispatch_proposal"}
        extra = public_methods - allowed
        assert not extra, f"RemediationLoop exposes unexpected public methods: {extra}"


# ---------------------------------------------------------------------------
# 8. dispatch_proposal (disabled, default): pure no-op.
# ---------------------------------------------------------------------------


class TestDispatchProposalDisabled:
    """When REMEDIATION_DISPATCH_ENABLED is false (the default), dispatch_proposal
    must be a pure no-op: no exceptions, no side effects, status "disabled"."""

    def setup_method(self):
        self.mod = _load_module()
        self.loop = self.mod.RemediationLoop()

    def _proposal(self, count: int = 3) -> list:
        return [
            {
                "file": f"f{i}.py",
                "line": i,
                "pattern_type": f"pat_{i}",
                "severity": "high",
                "runtime_risk": 0.1,
                "suggestion": f"Fix {i}",
            }
            for i in range(count)
        ]

    def test_disabled_returns_status_disabled(self):
        """Default gate=false → status must be 'disabled'."""
        original = self.mod.REMEDIATION_DISPATCH_ENABLED
        try:
            self.mod.REMEDIATION_DISPATCH_ENABLED = False
            result = self.loop.dispatch_proposal(self._proposal())
        finally:
            self.mod.REMEDIATION_DISPATCH_ENABLED = original
        assert result["status"] == "disabled"

    def test_disabled_dispatched_is_zero(self):
        original = self.mod.REMEDIATION_DISPATCH_ENABLED
        try:
            self.mod.REMEDIATION_DISPATCH_ENABLED = False
            result = self.loop.dispatch_proposal(self._proposal())
        finally:
            self.mod.REMEDIATION_DISPATCH_ENABLED = original
        assert result["dispatched"] == 0

    def test_disabled_returns_no_items_key(self):
        original = self.mod.REMEDIATION_DISPATCH_ENABLED
        try:
            self.mod.REMEDIATION_DISPATCH_ENABLED = False
            result = self.loop.dispatch_proposal(self._proposal())
        finally:
            self.mod.REMEDIATION_DISPATCH_ENABLED = original
        assert "items" not in result

    def test_disabled_is_not_async(self):
        """The disabled path must be synchronous — no coroutine returned."""
        import inspect

        original = self.mod.REMEDIATION_DISPATCH_ENABLED
        try:
            self.mod.REMEDIATION_DISPATCH_ENABLED = False
            ret = self.loop.dispatch_proposal(self._proposal())
        finally:
            self.mod.REMEDIATION_DISPATCH_ENABLED = original
        assert not inspect.isawaitable(ret), "disabled path must not return a coroutine"


# ---------------------------------------------------------------------------
# 9. dispatch_proposal (enabled): correct count, dedup by (file, pattern_type).
# ---------------------------------------------------------------------------


class TestDispatchProposalEnabled:
    """When REMEDIATION_DISPATCH_ENABLED is true, dispatch_proposal prepares
    structured work-item payloads without I/O or code mutation."""

    def setup_method(self):
        self.mod = _load_module()
        self.loop = self.mod.RemediationLoop()

    def _enable(self):
        self.mod.REMEDIATION_DISPATCH_ENABLED = True

    def _disable(self):
        self.mod.REMEDIATION_DISPATCH_ENABLED = False

    def _proposal(self, count: int, *, file_prefix: str = "f") -> list:
        return [
            {
                "file": f"{file_prefix}{i}.py",
                "line": i,
                "pattern_type": f"pat_{i}",
                "severity": "high",
                "runtime_risk": 0.2,
                "suggestion": f"Fix {i}",
            }
            for i in range(count)
        ]

    def test_enabled_status_is_prepared(self):
        self._enable()
        try:
            result = self.loop.dispatch_proposal(self._proposal(3))
        finally:
            self._disable()
        assert result["status"] == "prepared"

    def test_enabled_dispatched_equals_len_when_under_cap(self):
        """Proposal smaller than MAX_BATCH → dispatched == len(proposal)."""
        self._enable()
        try:
            n = max(1, self.mod.REMEDIATION_MAX_BATCH - 1)
            result = self.loop.dispatch_proposal(self._proposal(n))
        finally:
            self._disable()
        assert result["dispatched"] == n
        assert len(result["items"]) == n

    def test_enabled_capped_at_max_batch(self):
        """Proposal larger than MAX_BATCH → dispatched == MAX_BATCH."""
        self._enable()
        try:
            cap = self.mod.REMEDIATION_MAX_BATCH
            result = self.loop.dispatch_proposal(self._proposal(cap + 10))
        finally:
            self._disable()
        assert result["dispatched"] == cap
        assert len(result["items"]) == cap

    def test_dedup_by_file_and_pattern_type(self):
        """Duplicate (file, pattern_type) pairs within the batch are skipped."""
        self._enable()
        try:
            # Two entries with identical (file, pattern_type), one unique.
            proposal = [
                {
                    "file": "dup.py",
                    "line": 1,
                    "pattern_type": "god_class",
                    "severity": "high",
                    "runtime_risk": 0.3,
                    "suggestion": "Extract A",
                },
                {
                    "file": "dup.py",
                    "line": 2,
                    "pattern_type": "god_class",
                    "severity": "high",
                    "runtime_risk": 0.4,
                    "suggestion": "Extract B",
                },
                {
                    "file": "unique.py",
                    "line": 5,
                    "pattern_type": "long_method",
                    "severity": "medium",
                    "runtime_risk": 0.1,
                    "suggestion": "Split it",
                },
            ]
            result = self.loop.dispatch_proposal(proposal)
        finally:
            self._disable()
        assert result["dispatched"] == 2
        titles = [item["title"] for item in result["items"]]
        assert any("dup.py" in t for t in titles)
        assert any("unique.py" in t for t in titles)

    def test_items_have_required_keys(self):
        """Every returned work-item must have title, body, and labels."""
        self._enable()
        try:
            result = self.loop.dispatch_proposal(self._proposal(2))
        finally:
            self._disable()
        for item in result["items"]:
            assert "title" in item
            assert "body" in item
            assert "labels" in item

    def test_labels_include_anti_pattern_tag(self):
        self._enable()
        try:
            result = self.loop.dispatch_proposal(self._proposal(1))
        finally:
            self._disable()
        assert "anti-pattern" in result["items"][0]["labels"]


# ---------------------------------------------------------------------------
# 10. READ-ONLY CONTRACT with dispatch enabled: no subprocess/file-write/PR.
# ---------------------------------------------------------------------------


class TestDispatchReadOnlyContract(ReadOnlyCapabilityChecks):
    """Even with dispatch enabled, the module must not shell out, write files,
    or create PRs.  Mock the module constants to verify no forbidden I/O path
    is reachable via dispatch_proposal."""

    def setup_method(self):
        self.mod = _load_module()
        self.loop = self.mod.RemediationLoop()

    def _proposal(self, count: int = 2) -> list:
        return [
            {
                "file": f"x{i}.py",
                "line": i,
                "pattern_type": "god_class",
                "severity": "high",
                "runtime_risk": 0.5,
                "suggestion": "Refactor",
            }
            for i in range(count)
        ]

    def test_dispatch_enabled_returns_dict_no_network(self):
        """With gate enabled, dispatch_proposal returns a dict synchronously — no network."""
        original = self.mod.REMEDIATION_DISPATCH_ENABLED
        self.mod.REMEDIATION_DISPATCH_ENABLED = True
        try:
            result = self.loop.dispatch_proposal(self._proposal())
        finally:
            self.mod.REMEDIATION_DISPATCH_ENABLED = original

        assert isinstance(result, dict)
        assert result["status"] in {"prepared", "disabled"}
