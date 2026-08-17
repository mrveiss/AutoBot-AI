# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A cancelled ownership request must not leave `git blame` running (#14390).

The failure this pins is invisible from the caller's side. `asyncio.to_thread`
around a blocking `subprocess.run` unblocks the event loop, so the symptom
#13602 fixed stays fixed — but cancelling that await abandons the worker thread
while the child process keeps running. Nothing errors. The request returns. The
process is simply still there, holding a `git blame` on a large file until it
finishes on its own.

So these tests assert on **the child**, not on the coroutine:

* the process object reaches a terminated state after cancellation;
* `CancelledError` still propagates (swallowing it would report an abandoned
  request as a completed one);
* the child is reaped, not left as a zombie.

`_run_blame` is driven directly rather than through `_analyze_file_ownership`,
because the per-file loop would need a real repository and hundreds of blames to
reach the same seam — and the seam is what is under test.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).with_name("ownership_analyzer.py")


def _load_analyzer():
    """Load the analyzer without importing the `code_analysis` package.

    Registered in sys.modules before exec_module and popped after: the module
    declares dataclasses, and `dataclasses._is_type` resolves names through
    `sys.modules[cls.__module__]` when annotations are strings. A module
    executed out-of-band is absent from that table, and class creation dies on
    `'NoneType' object has no attribute '__dict__'` (#14194 hit exactly this).
    """
    name = "_ownership_analyzer_isolated_14390"
    spec = importlib.util.spec_from_file_location(name, _MODULE_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - path is fixed
        raise ImportError(f"could not load {_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.fixture(scope="module")
def analyzer_module():
    return _load_analyzer()


class _FakeProc:
    """An asyncio subprocess that never finishes until it is killed."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.kill_calls = 0
        self.wait_calls = 0

    async def communicate(self):
        await asyncio.Event().wait()  # never completes on its own
        raise AssertionError("unreachable")

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    async def wait(self) -> int:
        self.wait_calls += 1
        return self.returncode if self.returncode is not None else 0


async def _drive_until_started(module, proc, monkeypatch):
    """Start `_run_blame` against *proc* and yield once it is awaiting output."""

    async def _fake_exec(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", _fake_exec)
    task = asyncio.ensure_future(module.OwnershipAnalyzer._run_blame(Path("f.py"), Path(".")))
    await asyncio.sleep(0)  # let the coroutine reach `communicate()`
    await asyncio.sleep(0)
    return task


@pytest.mark.asyncio
async def test_cancelling_the_blame_kills_the_child(analyzer_module, monkeypatch):
    """The regression: the caller's cancellation must reach the process."""
    proc = _FakeProc()
    task = await _drive_until_started(analyzer_module, proc, monkeypatch)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert proc.kill_calls == 1, "the git blame child was never killed — it outlives the request"


@pytest.mark.asyncio
async def test_the_killed_child_is_reaped(analyzer_module, monkeypatch):
    """kill() alone leaves a zombie held by this event loop."""
    proc = _FakeProc()
    task = await _drive_until_started(analyzer_module, proc, monkeypatch)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert proc.wait_calls == 1, "kill() without wait() leaks a zombie"


@pytest.mark.asyncio
async def test_cancellation_still_propagates(analyzer_module, monkeypatch):
    """Killing the child must not swallow the signal.

    If `CancelledError` were absorbed, an abandoned request would be reported
    to every caller above as a completed one with no ownership data.
    """
    proc = _FakeProc()
    task = await _drive_until_started(analyzer_module, proc, monkeypatch)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_a_timeout_also_kills_the_child(analyzer_module, monkeypatch):
    """The per-file ceiling terminates too, and returns the no-data sentinel."""
    proc = _FakeProc()

    async def _fake_exec(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(analyzer_module.asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(analyzer_module, "_BLAME_TIMEOUT_SECONDS", 0.01)

    result = await analyzer_module.OwnershipAnalyzer._run_blame(Path("f.py"), Path("."))

    assert result is None
    assert proc.kill_calls == 1, "a timed-out blame must be killed, not abandoned"
    assert proc.wait_calls == 1


@pytest.mark.asyncio
async def test_an_already_exited_child_is_not_killed_twice(analyzer_module):
    """`_terminate` must tolerate a process that finished on its own."""
    proc = _FakeProc()
    proc.returncode = 0

    await analyzer_module.OwnershipAnalyzer._terminate(proc)

    assert proc.kill_calls == 0
    assert proc.wait_calls == 0
