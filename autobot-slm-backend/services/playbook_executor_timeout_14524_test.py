# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`execute_playbook` had no wall-clock timeout at all (#14524).

`PlaybookExecutor._run_subprocess` used to `await process.wait()` unwrapped by
any deadline -- the only timeouts anywhere in this file were on the
`_update_code_source` git helper, unrelated to the playbook run itself. A
single hung `ansible-playbook` (a genuinely stuck SSH connection or remote
task) blocked the caller -- for the reconciler's remediation path,
`_remediate_node` and therefore that node's slot in `_attempt_remediation`'s
serial pass -- indefinitely.

These tests drive the REAL `_run_subprocess`/`_kill_process_group` against
REAL (harmless, short-lived) subprocesses -- a mock subprocess cannot prove a
process group actually dies, only that a mock's methods were called. Per
test, what discriminates pre-#14524 code from this fix:

  - `_run_subprocess` takes no `timeout_s` parameter at all pre-fix, so every
    test below that passes it raises `TypeError` immediately, not merely
    "hangs" (a test that hangs is bad CI citizenship; this fails fast).
  - The process-group-kill mechanism itself was verified against a standalone
    (non-repo) prototype before being trusted here: a plain
    `process.send_signal(SIGTERM)` at the child's own PID -- the closest a
    naive first-pass fix might do without the `start_new_session=True` +
    `os.killpg` insight -- left BOTH the direct child and its backgrounded
    grandchild running; only the process-group kill implemented here reliably
    reaped both. That is the literal "orphaned ansible-playbook or SSH
    session" shape this fix exists to close.

The module is loaded from disk, like its `reconciler.py` siblings: the
package conftest stubs `services.*`, and a plain `import services.
playbook_executor` would yield a MagicMock that passes every assertion here
while exercising nothing.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_playbook_executor():
    spec = importlib.util.spec_from_file_location(
        "playbook_executor_under_timeout_test", _SLM_ROOT / "services" / "playbook_executor.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["playbook_executor_under_timeout_test"] = module
    spec.loader.exec_module(module)
    return module


playbook_executor = _load_real_playbook_executor()


def _proc_state(pid: int) -> str:
    """'gone', 'zombie', or 'alive' for *pid*, read from /proc.

    A killed process is briefly a zombie before something reaps it -- that is
    a normal, harmless OS transient, not the "still running / holding a
    session open" failure this fix targets. Either outcome proves the process
    is no longer doing work.
    """
    try:
        content = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
        return "gone"
    after_comm = content.rsplit(")", 1)[-1].split()
    state = after_comm[0] if after_comm else "?"
    return "zombie" if state == "Z" else "alive"


def _wait_until_dead(pid: int, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while True:
        if _proc_state(pid) in ("gone", "zombie"):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def test_the_real_module_was_loaded_not_a_stub():
    """`hasattr`/`callable` are true of any MagicMock and cannot tell the two apart."""
    assert not isinstance(playbook_executor.PlaybookExecutor, MagicMock)
    assert inspect.iscoroutinefunction(playbook_executor.PlaybookExecutor._run_subprocess)
    assert inspect.iscoroutinefunction(playbook_executor.PlaybookExecutor._kill_process_group)
    sig = inspect.signature(playbook_executor.PlaybookExecutor._run_subprocess)
    assert "timeout_s" in sig.parameters, "_run_subprocess must accept a timeout_s parameter (#14524)"
    sig = inspect.signature(playbook_executor.PlaybookExecutor.execute_playbook)
    assert "timeout_s" in sig.parameters, "execute_playbook must accept a timeout_s parameter (#14524)"


def test_run_subprocess_without_timeout_is_unaffected():
    """`timeout_s=None` (the default) must behave exactly as before -- deployment
    and provisioning runs (site.yml, update-all-nodes.yml) are legitimately
    long and explicitly out of this issue's scope; only a caller that opts in
    gets bounded.
    """
    executor = playbook_executor.PlaybookExecutor()

    async def _go():
        return await executor._run_subprocess(
            cmd=["/bin/sh", "-c", "echo hello-14524"],
            env=dict(os.environ),
            progress_callback=None,
        )

    result = asyncio.run(_go())
    assert result["returncode"] == 0
    assert result["timed_out"] is False
    assert "hello-14524" in result["output"]


def test_run_subprocess_timeout_kills_the_whole_process_group_and_reports_failure():
    """The core fix, exercised behaviourally (#14524).

    Spawns a process that (a) ignores SIGTERM and (b) backgrounds a `sleep`
    grandchild -- the shape of a real stuck ansible-playbook run with a
    still-open ssh child. `_run_subprocess` must come back well inside the
    timeout with a FAILED result, and BOTH pids must actually be dead
    afterwards -- not merely that a kill was attempted.

    Discriminates: pre-#14524, `_run_subprocess` has no `timeout_s`
    parameter at all, so this call raises `TypeError` immediately (this test
    fails, fast, not by hanging). Post-fix it passes.
    """
    executor = playbook_executor.PlaybookExecutor()
    # Short grace period so a SIGTERM-ignoring child escalates to SIGKILL
    # quickly -- this test must not itself take anywhere near the real
    # AUTOBOT_PLAYBOOK_KILL_GRACE_S default (5s) times two signal rounds.
    original_grace = playbook_executor.PLAYBOOK_KILL_GRACE_S
    playbook_executor.PLAYBOOK_KILL_GRACE_S = 0.3

    pid_dir = Path(f"/tmp/playbook_executor_14524_test_{os.getpid()}")
    pid_dir.mkdir(exist_ok=True)
    parent_pid_file = pid_dir / "parent.pid"
    child_pid_file = pid_dir / "child.pid"

    script = (
        "trap '' TERM\n"
        f"echo $$ > {parent_pid_file}\n"
        "sleep 30 &\n"
        "child=$!\n"
        f"echo $child > {child_pid_file}\n"
        "wait $child\n"
    )

    async def _go():
        return await executor._run_subprocess(
            cmd=["/bin/bash", "-c", script],
            env=dict(os.environ),
            progress_callback=None,
            timeout_s=0.5,
        )

    try:
        started = time.monotonic()
        result = asyncio.run(_go())
        elapsed = time.monotonic() - started

        assert result["timed_out"] is True
        assert result["returncode"] != 0
        # Bounded: timeout (0.5s) + at most two kill-grace windows (0.3s each),
        # with headroom for scheduling jitter -- never anywhere near the 30s
        # the hung sleep asked for.
        assert elapsed < 5, f"a timed-out run must return promptly, took {elapsed:.1f}s"

        for _ in range(100):
            if parent_pid_file.exists() and child_pid_file.exists():
                break
            time.sleep(0.02)
        parent_pid = int(parent_pid_file.read_text().strip())
        child_pid = int(child_pid_file.read_text().strip())

        assert _wait_until_dead(
            parent_pid, timeout_s=3
        ), "the direct child (ansible-playbook stand-in) survived the timeout"
        assert _wait_until_dead(
            child_pid, timeout_s=3
        ), "the grandchild (ssh-session stand-in) survived the timeout -- exactly the orphan this fix exists to prevent"
    finally:
        playbook_executor.PLAYBOOK_KILL_GRACE_S = original_grace
        for f in (parent_pid_file, child_pid_file):
            f.unlink(missing_ok=True)
        pid_dir.rmdir()


def test_kill_process_group_is_a_noop_on_an_already_exited_process():
    """No crash when the timeout races the process exiting on its own."""
    executor = playbook_executor.PlaybookExecutor()

    async def _go():
        process = await asyncio.create_subprocess_exec(
            "/bin/true",
            start_new_session=True,
        )
        await process.wait()
        # Already reaped -- os.getpgid(process.pid) now raises ProcessLookupError.
        await executor._kill_process_group(process)

    asyncio.run(_go())  # must not raise
