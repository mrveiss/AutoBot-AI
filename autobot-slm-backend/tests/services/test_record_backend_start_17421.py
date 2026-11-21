# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The builtin updater records the old backend's start before restarting it (#17421).

A real ``systemctl`` stand-in on PATH answers ``show -p ActiveEnterTimestamp --value --timestamp=unix``.
"""

from __future__ import annotations

import asyncio
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from autobot_shared import backend_start_marker as marker  # noqa: E402
from services.sync_restart import record_backend_start  # noqa: E402


def _fake_systemctl(bin_dir: Path, output: str) -> None:
    bin_dir.mkdir()
    script = bin_dir / "systemctl"
    script.write_text(f"#!/bin/sh\necho '{output}'\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def _record(monkeypatch, tmp_path: Path, output: str, services: list[str]) -> Path:
    _fake_systemctl(tmp_path / "bin", output)
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    target = tmp_path / "data" / "previous_backend_start"
    monkeypatch.setattr(marker, "marker_path", lambda: target)
    asyncio.run(record_backend_start(services))
    return target


def test_the_old_backends_start_is_recorded(tmp_path, monkeypatch) -> None:
    target = _record(monkeypatch, tmp_path, "@1763700000", ["autobot-backend"])
    assert marker.read_marker() == datetime.fromtimestamp(1763700000, tz=timezone.utc)
    assert target.exists()


def test_nothing_is_recorded_for_other_services_or_a_never_started_unit(tmp_path, monkeypatch) -> None:
    assert not _record(monkeypatch, tmp_path, "@1763700000", ["nginx"]).exists()
    assert not _record(monkeypatch, tmp_path / "second", "@0", ["autobot-backend"]).exists()
