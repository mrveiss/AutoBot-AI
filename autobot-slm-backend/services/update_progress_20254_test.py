# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A running self-update reports its position from its own log (#20254)."""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SECRET = "hunter2-very-secret"  # pragma: allowlist secret
_STARTED = "2026-10-31T10:00:00+00:00"
_NOW = datetime(2026, 10, 31, 10, 30, tzinfo=timezone.utc)


def _load(name: str):
    """Real modules by path, past the conftest's services stub."""
    spec = importlib.util.spec_from_file_location(f"services.{name}", _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def progress(monkeypatch):
    for name in ("self_update_log_reader", "update_report"):
        monkeypatch.delitem(sys.modules, f"services.{name}", raising=False)
        _load(name)
    return _load("update_progress")


def _log(tmp_path: Path, body: str, age_seconds: float = 5) -> Path:
    path = tmp_path / "self-update.log"
    path.write_text(f"SELF-UPDATE RUN STARTED {_STARTED}\n{body}", encoding="utf-8")
    moment = (_NOW - timedelta(seconds=age_seconds)).timestamp()
    os.utime(path, (moment, moment))
    return path


_RUNNING = "PLAY [first] ****\nTASK [one] ****\nok: [h]\nPLAY [second] ****\nTASK [install deps] ****\n"
_RECAP = _RUNNING + "PLAY RECAP ****\nh : ok=1 changed=0 unreachable=0 failed=0\n"


def test_a_live_run_reports_its_play_task_and_times(progress, tmp_path) -> None:
    out = progress.build_update_progress(_log(tmp_path, _RUNNING), True, now=_NOW)
    assert (out["state"], out["play"], out["task"]) == ("running", "second", "install deps")
    assert out["elapsed_seconds"] == 1800
    assert out["last_line_at"].startswith("2026-10-31T10:29:55")


def test_a_live_run_with_a_quiet_log_says_so(progress, tmp_path) -> None:
    log = _log(tmp_path, _RUNNING, age_seconds=progress.STALL_SECONDS + 1)
    assert progress.build_update_progress(log, True, now=_NOW)["state"] == "quiet"


def test_a_run_that_exited_with_no_recap_says_so(progress, tmp_path) -> None:
    assert progress.build_update_progress(_log(tmp_path, _RUNNING), False, now=_NOW)["state"] == "exited_without_recap"


def test_a_recap_is_finished_whatever_the_unit_says(progress, tmp_path) -> None:
    assert progress.build_update_progress(_log(tmp_path, _RECAP), False, now=_NOW)["state"] == "finished"


def test_a_unit_that_cannot_be_asked_is_unknown_not_healthy(progress, tmp_path) -> None:
    assert progress.build_update_progress(_log(tmp_path, _RUNNING), None, now=_NOW)["state"] == "unknown"


def test_an_older_runs_log_is_not_this_runs_progress(progress, tmp_path) -> None:
    out = progress.build_update_progress(_log(tmp_path, _RECAP), True, since="2026-10-31T11:00:00+00:00", now=_NOW)
    assert out == {"state": "waiting", "play": None, "task": None, "last_line_at": None, "elapsed_seconds": None}


def test_no_log_is_waiting(progress, tmp_path) -> None:
    assert progress.build_update_progress(tmp_path / "absent.log", True, now=_NOW)["state"] == "waiting"


def test_names_are_redacted(progress, tmp_path) -> None:
    body = f"PLAY [p password={_SECRET}] ****\nTASK [t token={_SECRET}] ****\n"  # pragma: allowlist secret
    out = progress.build_update_progress(_log(tmp_path, body), True, now=_NOW)
    assert _SECRET not in str(out)
