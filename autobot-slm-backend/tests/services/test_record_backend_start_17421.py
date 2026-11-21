# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The builtin updater records the old backend's start before restarting it (#17421).

A real ``systemctl`` stand-in on PATH records its arguments and answers
``show -p ActiveEnterTimestamp --value --timestamp=unix``. The updater writes where the backend reads,
although the two processes are configured through different variables.
"""

from __future__ import annotations

import asyncio
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from autobot_shared import backend_start_marker as marker  # noqa: E402
from services import sync_restart  # noqa: E402

UNIX = 1763700000


def _fake_systemctl(bin_dir: Path, body: str) -> Path:
    bin_dir.mkdir(parents=True)
    argv_log = bin_dir / "argv"
    script = bin_dir / "systemctl"
    script.write_text(f'#!/bin/sh\necho "$@" > "{argv_log}"\n{body}\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return argv_log


def _setup(monkeypatch, tmp_path: Path, body: str, services: list[str]) -> tuple[Path, Path]:
    argv_log = _fake_systemctl(tmp_path / "bin", body)
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    data_dir = tmp_path / "var-lib-autobot"
    # The updater is configured with SLM_BACKEND_DATA_DIR; the backend reads its own AUTOBOT_DATA_DIR
    # (config.path.data_path). Different settings that name the same directory.
    monkeypatch.setattr(sync_restart, "BACKEND_DATA_DIR", str(data_dir))
    monkeypatch.setattr(marker.config.path, "data_dir", str(data_dir))
    asyncio.run(sync_restart.record_backend_start(services))
    return argv_log, data_dir / "previous_backend_start"


def test_the_updater_writes_where_the_backend_reads(tmp_path, monkeypatch) -> None:
    argv_log, target = _setup(monkeypatch, tmp_path, f"echo @{UNIX}", ["autobot-backend"])
    assert argv_log.read_text(encoding="utf-8").split() == [
        "show",
        "-p",
        "ActiveEnterTimestamp",
        "--value",
        "--timestamp=unix",
        "autobot-backend",
    ]
    assert target.exists()
    assert marker.marker_path() == target, "the reader's default path is the writer's"
    assert marker.read_marker() == datetime.fromtimestamp(UNIX, tz=timezone.utc)


def test_nothing_is_recorded_for_other_services_or_a_never_started_unit(tmp_path, monkeypatch) -> None:
    assert not _setup(monkeypatch, tmp_path / "a", f"echo @{UNIX}", ["nginx"])[1].exists()
    assert not _setup(monkeypatch, tmp_path / "b", "echo @0", ["autobot-backend"])[1].exists()


def test_a_failing_systemctl_records_nothing_and_does_not_raise(tmp_path, monkeypatch) -> None:
    assert not _setup(monkeypatch, tmp_path, "exit 1", ["autobot-backend"])[1].exists()


def test_a_hung_systemctl_is_killed_at_the_timeout_and_never_blocks_the_restart(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sync_restart, "SYSTEMCTL_TIMEOUT_S", 0.3)
    started = time.monotonic()
    _, target = _setup(monkeypatch, tmp_path, "sleep 30", ["autobot-backend"])
    assert time.monotonic() - started < 10
    assert not target.exists()
