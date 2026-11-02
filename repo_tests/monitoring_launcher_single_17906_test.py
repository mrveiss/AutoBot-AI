# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One monitoring launcher (#17906).

``start_monitoring.py`` and ``start_hardware_monitoring.py`` each carried their own manager, optimization
loop and dashboard loop; a fix to one (#14129) never reached the other (#15643). The logic now lives once in
``start_monitoring.py``; the hardware behaviour is its ``--backend hardware`` flag, and the second file is gone.

Two checks: the loops are DEFINED once (syntax tree, so prose naming them is not a definition), and the hardware
backend is actually TAKEN -- the launcher is run against stub monitors and the hardware ones are the ones called.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import sys
import tempfile
import types
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

MONITORING_DIR = repo_root() / "autobot-infrastructure" / "shared" / "scripts" / "monitoring"
LAUNCHER = MONITORING_DIR / "start_monitoring.py"
RETIRED_LAUNCHER = MONITORING_DIR / "start_hardware_monitoring.py"
MARKERS = ("_periodic_optimization_loop", "_dashboard_update_loop")
MIN_SCRIPTS = 1  # the one launcher; a vanished directory must fail, not pass empty


def _defined(source: str) -> set[str]:
    """Names of the marker functions DEFINED (not merely mentioned) in *source*."""
    tree = ast.parse(source)
    return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))} & set(MARKERS)


def _scripts() -> list[Path]:
    return sorted(p for p in MONITORING_DIR.glob("*.py") if not p.name.endswith("_test.py"))


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a definition", "class M:\n    async def _dashboard_update_loop(self): ...\n", {"_dashboard_update_loop"}),
        ("a call", "self._dashboard_update_loop()\n", set()),
        ("a comment", "# async def _periodic_optimization_loop(self): ...\nx = 1\n", set()),
    ],
)
def test_the_matcher_tells_a_definition_from_a_mention(label: str, source: str, expected: set[str]) -> None:
    assert _defined(source) == expected, label


def test_the_loops_are_defined_in_exactly_one_launcher() -> None:
    scripts = _scripts()
    assert len(scripts) >= MIN_SCRIPTS, f"found {len(scripts)} monitoring scripts under {MONITORING_DIR}"
    owners = {p.name for p in scripts if _defined(p.read_text(encoding="utf-8"))}
    assert owners == {LAUNCHER.name}, (
        f"#17906: {sorted(owners)} define the monitoring loops; they live once in {LAUNCHER.name}. "
        "Select behaviour with a backend, do not copy the manager."
    )


def _stub(name: str, **attrs: object) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


@pytest.fixture()
def launcher(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """The launcher loaded against stub monitors that record which backend was driven."""
    calls: list[str] = []

    async def acall(label: str, result: object = None) -> object:
        calls.append(label)
        return result

    def sync_note(label: str, result: object = None) -> object:
        calls.append(label)
        return result

    perf = _stub(
        "utils.performance_monitor",
        performance_monitor=types.SimpleNamespace(npu_available=False),
        start_monitoring=lambda: acall("perf.start"),
        stop_monitoring=lambda: acall("perf.stop"),
        collect_metrics=lambda: acall("perf.collect", {"collection_successful": True}),
        get_performance_dashboard=lambda: acall("perf.dashboard", {}),
        add_alert_callback=lambda cb: acall("perf.alert"),
    )
    hw = _stub(
        "utils.hardware_metrics",
        hardware_monitor=types.SimpleNamespace(npu_available=False),
        start_hardware_monitoring=lambda: acall("hw.start"),
        stop_hardware_monitoring=lambda: acall("hw.stop"),
        collect_phase9_metrics=lambda: acall("hw.collect", {"collection_successful": True}),
        get_phase9_performance_dashboard=lambda: sync_note("hw.dashboard", {}),
        add_phase9_alert_callback=lambda cb: sync_note("hw.alert"),
    )
    gpu = _stub(
        "utils.gpu_acceleration_optimizer",
        benchmark_gpu=lambda: acall("gpu"),
        get_gpu_capabilities=lambda: {"gpu_available": False},
        gpu_optimizer=types.SimpleNamespace(gpu_available=False),
        monitor_gpu_efficiency=lambda: acall("eff", {}),
        optimize_gpu_for_multimodal=lambda: acall("opt"),
    )
    utils = _stub("utils")
    utils.__path__ = []
    utils.hardware_metrics, utils.performance_monitor = hw, perf
    for mod in (utils, perf, hw, gpu):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    monkeypatch.setattr(sys, "path", [str(repo_root() / "autobot-backend"), *sys.path])
    spec = importlib.util.spec_from_file_location("start_monitoring_under_test_17906", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))  # read by monitoring_backends
    return module, calls


def _run_start(module, name: str) -> None:
    async def go() -> None:
        manager = module.PerformanceMonitoringManager(module.load_backend(name))
        manager.config["gpu_optimization_enabled"] = False
        manager.config["realtime_dashboard_enabled"] = False
        assert await manager.initialize()
        assert await manager.start_monitoring()
        assert await manager.stop_monitoring()

    asyncio.run(go())


def test_the_hardware_backend_is_taken_not_just_parsed(launcher) -> None:
    module, calls = launcher
    _run_start(module, "hardware")
    assert calls == ["hw.alert", "hw.collect", "hw.start", "hw.stop"]


def test_the_default_backend_still_drives_the_performance_monitor(launcher) -> None:
    module, calls = launcher
    _run_start(module, "performance")
    assert calls == ["perf.alert", "perf.collect", "perf.start", "perf.stop"]


def test_the_hardware_backend_keeps_its_log_and_report_locations(launcher, tmp_path: Path) -> None:
    module, _ = launcher
    backend = module.load_backend("hardware")
    assert backend.log_file == tmp_path / "hardware_monitoring.log"
    assert (backend.report_dir, backend.report_prefix) == (tmp_path, "hardware_benchmark")
    assert backend.task_prefix == "hw-monitor"


def test_an_unknown_backend_is_refused(launcher) -> None:
    module, _ = launcher
    with pytest.raises(ValueError, match="unknown monitoring backend"):
        module.load_backend("phase9")


def test_the_hardware_launcher_is_a_flag_on_the_one_launcher(launcher, monkeypatch: pytest.MonkeyPatch) -> None:
    """The retired file is gone, and ``--backend hardware`` on the command line selects the hardware backend."""
    module, _ = launcher
    assert not RETIRED_LAUNCHER.exists(), f"{RETIRED_LAUNCHER.name} is back; use start_monitoring.py --backend hardware"
    seen: list[str] = []
    monkeypatch.setattr(module, "configure_logging", lambda backend: seen.append(backend.name))
    monkeypatch.setattr(sys, "argv", [LAUNCHER.name, "--backend", "hardware", "status"])
    asyncio.run(module.main())
    assert seen == ["hardware"]
