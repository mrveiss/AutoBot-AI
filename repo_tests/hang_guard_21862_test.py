# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The hang guard kills a stalled or runaway process and spares a slow one (#21862, #21910)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from repo_tests import _hang_guard
from repo_tests._paths import repo_root


def test_a_quick_process_returns_its_output_and_status() -> None:
    done = _hang_guard.run_guarded([sys.executable, "-c", "print('ok')"], cwd=repo_root())
    assert done.returncode == 0 and done.stdout.strip() == "ok"


def test_a_process_using_no_cpu_is_killed_as_stalled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hang_guard, "STALL_SECONDS", 2.0)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        _hang_guard.run_guarded([sys.executable, "-c", "import time; time.sleep(60)"], cwd=repo_root())
    assert "no CPU progress" in str(caught.value.output)


def test_a_cpu_runaway_is_killed_on_its_cpu_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hang_guard, "CPU_BUDGET_SECONDS", 1.0)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        _hang_guard.run_guarded([sys.executable, "-c", "while True: pass"], cwd=repo_root())
    assert "over the" in str(caught.value.output)


def test_a_parent_waiting_on_a_cpu_busy_child_is_not_stalled(monkeypatch: pytest.MonkeyPatch) -> None:
    """The busy work is in a LIVE child, so only the process-tree scan sees the CPU."""
    monkeypatch.setattr(_hang_guard, "STALL_SECONDS", 5.0)
    monkeypatch.setattr(_hang_guard, "CPU_BUDGET_SECONDS", 120.0)  # own budget: 10 s of work must never trip it
    spin = "import time; t=time.process_time()\nwhile time.process_time()-t<10: pass"
    done = _hang_guard.run_guarded(["bash", "-c", f"{sys.executable} -c '{spin}'; true"], cwd=repo_root())
    assert done.returncode == 0


class _FakeProc:
    """A scripted /proc: ``reads`` maps pid -> list of stat-field lists, consumed one per read."""

    def __init__(self, tmp_path: Path, reads: dict[int, list[list[str]]]) -> None:
        self.reads = reads
        self.entries = [tmp_path / str(pid) for pid in reads]
        for entry in self.entries:
            entry.mkdir()

    def stat_fields(self, entry: Path) -> list[str] | None:
        script = self.reads[int(entry.name)]
        return script.pop(0) if len(script) > 1 else script[0]


def _stat(session: int, utime: int, stime: int, cutime: int, cstime: int) -> list[str]:
    fields = ["0"] * 20
    fields[3], fields[11], fields[12], fields[13], fields[14] = map(str, (session, utime, stime, cutime, cstime))
    return fields


def test_a_child_reaped_between_reads_is_counted_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Child 101 is read live (5 ticks), then reaped: the parent's cstime then holds those same 5 ticks."""
    reads = {
        101: [_stat(100, 5, 0, 0, 0), _stat(100, 5, 0, 0, 0)],  # live on its first read ...
        100: [_stat(100, 1, 0, 0, 5)],  # ... parent already shows the reaped 5 on every read
    }
    fake = _FakeProc(tmp_path, reads)
    # child is gone from /proc by the second pass (raises nothing: vanished -> None)
    calls = {"child": 0}

    def stat_fields(entry: Path) -> list[str] | None:
        if entry.name == "101":
            calls["child"] += 1
            return reads[101][0] if calls["child"] == 1 else None
        return fake.stat_fields(entry)

    monkeypatch.setattr(
        _hang_guard, "_PROC", type("P", (), {"is_dir": lambda s: True, "glob": lambda s, _p: fake.entries})()
    )
    monkeypatch.setattr(_hang_guard, "_stat_fields", stat_fields)
    ticks = _hang_guard.cpu_seconds(100) * _hang_guard._CLOCK_TICKS
    assert round(ticks) == 6  # parent utime 1 + the child's 5 once, never 11


def _patch_fake_proc(monkeypatch: pytest.MonkeyPatch, fake: _FakeProc, stat_fields) -> None:
    monkeypatch.setattr(
        _hang_guard, "_PROC", type("P", (), {"is_dir": lambda s: True, "glob": lambda s, _p: fake.entries})()
    )
    monkeypatch.setattr(_hang_guard, "_stat_fields", stat_fields)


def test_a_child_reaped_before_the_parent_reaps_it_counts_only_the_parents_own_ticks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Realistic race: child exits between the passes, the parent's pass-1 cutime is still 0."""
    fake = _FakeProc(tmp_path, {100: [_stat(100, 1, 0, 0, 0)], 101: [_stat(100, 5, 0, 0, 0)]})
    seen = {"child": 0}

    def stat_fields(entry: Path) -> list[str] | None:
        if entry.name == "101":
            seen["child"] += 1
            return _stat(100, 5, 0, 0, 0) if seen["child"] <= 2 else None  # live in listing + pass 1, gone by pass 2
        return fake.stat_fields(entry)

    _patch_fake_proc(monkeypatch, fake, stat_fields)
    assert round(_hang_guard.cpu_seconds(100) * _hang_guard._CLOCK_TICKS) == 1


def test_a_member_that_left_the_session_before_pass_one_adds_no_reaped_ticks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeProc(tmp_path, {100: [_stat(100, 1, 0, 0, 0)], 101: [_stat(100, 0, 0, 7, 0)]})
    seen = {"child": 0}

    def stat_fields(entry: Path) -> list[str] | None:
        if entry.name == "101":
            seen["child"] += 1
            return _stat(100 if seen["child"] == 1 else 999, 0, 0, 7, 0)  # member when listed, elsewhere after
        return fake.stat_fields(entry)

    _patch_fake_proc(monkeypatch, fake, stat_fields)
    assert round(_hang_guard.cpu_seconds(100) * _hang_guard._CLOCK_TICKS) == 1


def _group_gone(pgid: int) -> bool:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def test_an_exception_while_monitoring_kills_the_group_and_reaps(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[subprocess.Popen] = []

    def boom(proc: subprocess.Popen, state, now):
        seen.append(proc)
        raise KeyboardInterrupt

    monkeypatch.setattr(_hang_guard, "_poll", boom)
    with pytest.raises(KeyboardInterrupt):
        _hang_guard.run_guarded(["bash", "-c", "sleep 60 & sleep 60"], cwd=repo_root())
    proc = seen[0]
    assert proc.returncode is not None and proc.stdout.closed and proc.stderr.closed
    assert _group_gone(proc.pid)


def _kill_escaped_sleeper(pidfile: Path) -> None:
    """Kill the sleeper this test started, found by the pid it wrote, only if it is still a ``sleep``."""
    try:
        pid = int(pidfile.read_text(encoding="utf-8").strip())
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[0]
    except (OSError, ValueError):
        return  # never started, or already gone
    if os.path.basename(cmdline) == b"sleep":
        os.kill(pid, signal.SIGKILL)


def test_a_descendant_escaping_the_group_with_the_pipe_cannot_hang_the_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_hang_guard, "STALL_SECONDS", 2.0)
    monkeypatch.setattr(_hang_guard, "DRAIN_SECONDS", 1.0)
    pidfile = tmp_path / "escaped.pid"
    script = f"setsid sleep 40 & echo $! > {pidfile}; sleep 60"
    began = time.monotonic()
    try:
        with pytest.raises(subprocess.TimeoutExpired) as caught:
            _hang_guard.run_guarded(["bash", "-c", script], cwd=repo_root())
        assert time.monotonic() - began < 25  # the escaped sleep holds the pipe for 40 s
        assert "no CPU progress" in str(caught.value.output)
    finally:
        _kill_escaped_sleeper(pidfile)


def test_a_cleanup_failure_does_not_replace_the_original_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(proc: subprocess.Popen, state, now):
        raise KeyboardInterrupt

    def bad_reap(proc: subprocess.Popen) -> None:
        proc.kill()
        proc.wait()
        raise RuntimeError("reap failed")

    monkeypatch.setattr(_hang_guard, "_poll", boom)
    monkeypatch.setattr(_hang_guard, "_close_and_reap", bad_reap)
    with pytest.raises(KeyboardInterrupt) as caught:
        _hang_guard.run_guarded(["bash", "-c", "sleep 60"], cwd=repo_root())
    assert any("reap failed" in note for note in caught.value.__notes__)


def test_an_unreapable_child_raises_instead_of_hanging(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Stuck:
        pid = 1
        stdout = stderr = None

        def kill(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            assert timeout is not None, "unbounded wait would hang forever"
            raise subprocess.TimeoutExpired("x", timeout)

    monkeypatch.setattr(_hang_guard, "DRAIN_SECONDS", 1.0)
    with pytest.raises(RuntimeError, match="could not reap"):
        _hang_guard._close_and_reap(_Stuck())


def test_partial_output_and_stderr_survive_a_drain_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = subprocess.TimeoutExpired("x", 1.0, output=b"partial-out", stderr=b"partial-err")
    monkeypatch.setattr(_hang_guard, "_kill_and_drain", lambda proc: (_ for _ in ()).throw(exc))
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        _hang_guard._raise_killed(None, ["x"], "stalled", time.monotonic())  # type: ignore[arg-type]
    assert "partial-out" in caught.value.output and caught.value.stderr == "partial-err"
