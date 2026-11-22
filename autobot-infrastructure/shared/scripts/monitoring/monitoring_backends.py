#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two monitors ``start_monitoring.py`` can drive, behind one async surface (#17906).

Split out of the launcher so it stays under the file-size limit: the launcher owns the manager and its
loops, this module owns which backend monitor they call. Each backend imports its backend modules only
when selected, so choosing one never imports the other.

A backend tool (#18288): it resolves the backend's ``utils.*`` itself, so it puts the backend and the
repository root on its own path, exactly as the launcher does.
"""

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

# `project_root` is also the DATA root for the performance backend's logs/ and reports/ (#15643).
project_root = Path(__file__).resolve().parents[4]
backend_root = Path(__file__).resolve().parents[4] / "autobot-backend"
sys.path.insert(0, str(backend_root))
sys.path.insert(0, str(project_root))

BACKEND_PERFORMANCE = "performance"
BACKEND_HARDWARE = "hardware"
BACKENDS = (BACKEND_PERFORMANCE, BACKEND_HARDWARE)


@dataclass(frozen=True)
class MonitoringBackend:
    """The monitor a launcher drives, behind one async surface.

    The two backends differ in what they call, not in what the launcher does: the hardware
    functions are partly synchronous, so they are wrapped here and the manager awaits one shape.
    """

    name: str
    monitor: Any
    start: Callable[[], Awaitable[Any]]
    stop: Callable[[], Awaitable[Any]]
    collect: Callable[[], Awaitable[dict]]
    dashboard: Callable[[], Awaitable[dict]]
    add_alert_callback: Callable[[Callable], Awaitable[Any]]
    log_file: Path
    report_dir: Path
    report_prefix: str
    task_prefix: str


def _performance_backend() -> MonitoringBackend:
    from utils.performance_monitor import (
        add_alert_callback,
        collect_metrics,
        get_performance_dashboard,
        performance_monitor,
        start_monitoring,
        stop_monitoring,
    )

    return MonitoringBackend(
        name=BACKEND_PERFORMANCE,
        monitor=performance_monitor,
        start=start_monitoring,
        stop=stop_monitoring,
        collect=collect_metrics,
        dashboard=get_performance_dashboard,
        add_alert_callback=add_alert_callback,
        log_file=project_root / "logs" / "monitoring" / "monitoring.log",
        report_dir=project_root / "reports" / "performance",
        report_prefix="performance_benchmark",
        task_prefix="monitor",
    )


def _hardware_backend() -> MonitoringBackend:
    from utils import hardware_metrics as hw

    async def dashboard() -> dict:
        return hw.get_phase9_performance_dashboard()

    async def add_alert_callback(callback: Callable) -> None:
        hw.add_phase9_alert_callback(callback)

    # The hardware launcher has always written to the system temp dir, not the repository's
    # logs/ and reports/ trees; kept so existing readers of those files still find them.
    tmp = Path(tempfile.gettempdir())
    return MonitoringBackend(
        name=BACKEND_HARDWARE,
        monitor=hw.hardware_monitor,
        start=hw.start_hardware_monitoring,
        stop=hw.stop_hardware_monitoring,
        collect=hw.collect_phase9_metrics,
        dashboard=dashboard,
        add_alert_callback=add_alert_callback,
        log_file=tmp / "hardware_monitoring.log",
        report_dir=tmp,
        report_prefix="hardware_benchmark",
        task_prefix="hw-monitor",
    )


_BACKEND_FACTORIES = {BACKEND_PERFORMANCE: _performance_backend, BACKEND_HARDWARE: _hardware_backend}


def load_backend(name: str) -> MonitoringBackend:
    """Resolve *name* to its backend, importing only that backend's modules."""
    try:
        factory = _BACKEND_FACTORIES[name]
    except KeyError:
        raise ValueError(f"unknown monitoring backend {name!r}; expected one of {BACKENDS}") from None
    return factory()
