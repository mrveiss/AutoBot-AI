# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services/process_divergence.py (#15323).

The root conftest (autobot-slm-backend/conftest.py) real-loads
``services.process_divergence`` (and its ``services.deploy_artifacts``
dependency) rather than the usual MagicMock stub, so a plain
``from services.process_divergence import ...`` exercises the genuine
detector here.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from services.process_divergence import (
    _component_divergence,
    _newest_py_mtime,
    _service_active_since_epoch,
    compute_process_divergence,
    invalidate_process_divergence_cache,
)


def _run(coro):
    # Dedicated loop per call (matches the _code_sync_import helper pattern):
    # resilient when a prior test in the same session has closed the
    # main-thread event loop.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _monotonic_us_to_stdout(value_us: int) -> bytes:
    return str(value_us).encode()


# ---------------------------------------------------------------------------
# _newest_py_mtime
# ---------------------------------------------------------------------------


def test_newest_py_mtime_returns_none_for_missing_dir(tmp_path) -> None:
    assert _newest_py_mtime(str(tmp_path / "absent")) is None


def test_newest_py_mtime_returns_none_when_no_py_files(tmp_path) -> None:
    (tmp_path / "readme.txt").write_text("hi", encoding="utf-8")
    assert _newest_py_mtime(str(tmp_path)) is None


def test_newest_py_mtime_finds_newest_across_subdirs(tmp_path) -> None:
    older = tmp_path / "a.py"
    older.write_text("x", encoding="utf-8")
    sub = tmp_path / "pkg"
    sub.mkdir()
    newer = sub / "b.py"
    newer.write_text("y", encoding="utf-8")

    older_time = time.time() - 100
    newer_time = time.time()
    import os

    os.utime(older, (older_time, older_time))
    os.utime(newer, (newer_time, newer_time))

    result = _newest_py_mtime(str(tmp_path))
    assert result == newer.stat().st_mtime


def test_newest_py_mtime_skips_artifact_dirs(tmp_path) -> None:
    """A .py file under __pycache__ must never count as source (#15323)."""
    cache_dir = tmp_path / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "mod.cpython-310.py").write_text("compiled", encoding="utf-8")

    assert _newest_py_mtime(str(tmp_path)) is None


# ---------------------------------------------------------------------------
# _service_active_since_epoch
# ---------------------------------------------------------------------------


def test_service_active_since_epoch_returns_none_on_unparsable_output() -> None:
    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"n/a", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        result = _run(_service_active_since_epoch("autobot-backend"))
    assert result is None


def test_service_active_since_epoch_returns_none_when_unit_never_activated() -> None:
    """ActiveEnterTimestampMonotonic of 0 means never active (#15323) — must
    read as unknown, never as "started right now"."""

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"0", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        result = _run(_service_active_since_epoch("autobot-backend"))
    assert result is None


def test_service_active_since_epoch_returns_none_on_subprocess_error() -> None:
    async def _fake_exec(*cmd, **kw):
        raise OSError("systemctl not found")

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        result = _run(_service_active_since_epoch("autobot-backend"))
    assert result is None


def test_service_active_since_epoch_converts_monotonic_to_wallclock() -> None:
    """A unit that became active 10s ago (monotonic) resolves near time.time() - 10."""
    now_mono_us = int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000)
    active_us = now_mono_us - 10_000_000

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(_monotonic_us_to_stdout(active_us), b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        result = _run(_service_active_since_epoch("autobot-backend"))

    assert result is not None
    assert abs(result - (time.time() - 10)) < 2.0


# ---------------------------------------------------------------------------
# _component_divergence / compute_process_divergence — stale / healthy / unknown
# ---------------------------------------------------------------------------


def test_component_divergence_unknown_when_deployed_dir_missing() -> None:
    result = _run(_component_divergence("autobot-backend", "autobot-backend", None))
    assert result == "unknown"


def test_component_divergence_unknown_when_no_py_files(tmp_path) -> None:
    result = _run(_component_divergence("autobot-backend", "autobot-backend", str(tmp_path)))
    assert result == "unknown"


def test_component_divergence_unknown_when_service_active_since_undeterminable(tmp_path) -> None:
    """A detector that cannot resolve the process side must answer unknown —
    NEVER healthy — even though the file side resolved cleanly (#15323)."""
    (tmp_path / "app.py").write_text("x", encoding="utf-8")

    with patch("services.process_divergence._service_active_since_epoch", AsyncMock(return_value=None)):
        result = _run(_component_divergence("autobot-backend", "autobot-backend", str(tmp_path)))

    assert result == "unknown"


def test_component_divergence_stale_when_file_newer_than_process_start(tmp_path) -> None:
    (tmp_path / "app.py").write_text("x", encoding="utf-8")
    file_mtime = (tmp_path / "app.py").stat().st_mtime

    with patch(
        "services.process_divergence._service_active_since_epoch",
        AsyncMock(return_value=file_mtime - 60),
    ):
        result = _run(_component_divergence("autobot-backend", "autobot-backend", str(tmp_path)))

    assert result == "stale"


def test_component_divergence_healthy_when_process_started_after_newest_file(tmp_path) -> None:
    (tmp_path / "app.py").write_text("x", encoding="utf-8")
    file_mtime = (tmp_path / "app.py").stat().st_mtime

    with patch(
        "services.process_divergence._service_active_since_epoch",
        AsyncMock(return_value=file_mtime + 60),
    ):
        result = _run(_component_divergence("autobot-backend", "autobot-backend", str(tmp_path)))

    assert result == "healthy"


def test_compute_process_divergence_scans_all_components_and_caches(tmp_path) -> None:
    (tmp_path / "app.py").write_text("x", encoding="utf-8")
    file_mtime = (tmp_path / "app.py").stat().st_mtime
    calls: list[str] = []

    async def _fake_active_since(unit):
        calls.append(unit)
        return file_mtime + 60

    invalidate_process_divergence_cache()
    with patch("services.process_divergence._service_active_since_epoch", side_effect=_fake_active_since):
        first = _run(
            compute_process_divergence(
                {"autobot-backend": "autobot-backend"},
                {"autobot-backend": str(tmp_path)},
                force=True,
            )
        )
        second = _run(
            compute_process_divergence(
                {"autobot-backend": "autobot-backend"},
                {"autobot-backend": str(tmp_path)},
            )
        )

    assert first == {"autobot-backend": "healthy"}
    assert second == first
    assert calls == ["autobot-backend"], "second call within the TTL must hit the cache, not re-scan"


def test_compute_process_divergence_one_bad_component_reports_unknown_not_crash(tmp_path) -> None:
    """A component whose scan raises must degrade to unknown for THAT
    component only — one bad entry must never break the whole /status scan
    (#15323, mirrors _compute_stale_components' defensive per-component try)."""
    (tmp_path / "app.py").write_text("x", encoding="utf-8")

    async def _boom(unit):
        raise RuntimeError("systemd unreachable")

    invalidate_process_divergence_cache()
    with patch("services.process_divergence._service_active_since_epoch", side_effect=_boom):
        result = _run(
            compute_process_divergence(
                {"autobot-backend": "autobot-backend"},
                {"autobot-backend": str(tmp_path)},
                force=True,
            )
        )

    assert result == {"autobot-backend": "unknown"}
