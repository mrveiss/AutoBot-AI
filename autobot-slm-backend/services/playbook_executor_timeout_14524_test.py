# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`execute_playbook` had no wall-clock timeout at all (#14524).

`PlaybookExecutor._run_subprocess` used to `await process.wait()` unwrapped by
any deadline -- originally the only timeouts anywhere in this file were on
the `_update_code_source` git helper (30s/10s per command), unrelated to the
playbook run itself. A single hung `ansible-playbook` (a genuinely stuck SSH
connection or remote task) blocked the caller -- for the reconciler's
remediation path, `_remediate_node` and therefore that node's slot in
`_attempt_remediation`'s serial pass -- indefinitely.

Round 2 review found `_update_code_source`'s OWN existing timeouts shared the
same underlying flaw one level down (a lone `proc.kill()`/un-wrapped retry
`communicate()` reaches only git's own pid, not a surviving ssh/credential-
helper child) -- `_run_git`/`_log_updated_head_commit` now route through the
same `_kill_process_group` these tests cover directly.

These tests drive the REAL `_run_subprocess`/`_kill_process_group` against
REAL (harmless, short-lived) subprocesses -- a mock subprocess cannot prove a
process group actually dies, only that a mock's methods were called. Three
process-tree shapes, all found to matter by review round 2 (Cases A/B/C
below are its own naming):

  - Case A: the direct child ignores SIGTERM and backgrounds a sibling that
    does not trap anything itself, reachable only via a process-group signal.
    Verified against a standalone (non-repo) prototype before being trusted
    here: a plain `process.send_signal(SIGTERM)` at the child's own PID --
    the closest a naive first-pass fix might do without the
    `start_new_session=True` + `os.killpg` insight -- left BOTH processes
    running; the process-group kill reliably reaped both.
  - Case B: the direct pid is ALREADY REAPED (the leader exited on its own)
    while a sibling is still alive -- the only way an ATTACHED run wedges
    AFTER ansible itself has exited. The original `os.getpgid(process.pid)`
    lookup here raised `ProcessLookupError` and returned, killing nothing.
  - Case C: the direct child dies on the FIRST SIGTERM while a sibling
    ignores it. The original SIGTERM/SIGKILL escalation loop awaited the
    direct pid only, saw it reaped, and returned -- SIGKILL was never sent to
    the survivor (3/3 in review's own reproduction).

Per test, what discriminates pre-#14524 code from this fix: `_run_subprocess`
takes no `timeout_s` parameter at all pre-fix, so every test below that
passes it raises `TypeError` immediately, not merely "hangs" (a test that
hangs is bad CI citizenship; this fails fast). Cases B and C additionally
discriminate against the FIRST (round 1) version of `_kill_process_group`
itself, which fixed Case A but not B or C.

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


def test_run_subprocess_without_timeout_is_unaffected(tmp_path):
    """`timeout_s=None` (the default) must behave exactly as before -- deployment
    and provisioning runs (site.yml, update-all-nodes.yml) are legitimately
    long and explicitly out of this issue's scope; only a caller that opts in
    gets bounded.

    `ansible_dir=tmp_path` (CI finding): a bare `PlaybookExecutor()` resolves
    `ansible_dir` to `/opt/autobot/...`, which does not exist on a CI runner
    -- `_run_subprocess`'s `cwd=str(self.ansible_dir)` then fails the spawn
    itself with `FileNotFoundError`, before `timeout_s` is ever reached. A
    real, existing directory is what this test needs, not a specific one.
    """
    executor = playbook_executor.PlaybookExecutor(ansible_dir=tmp_path)

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


def test_run_subprocess_timeout_kills_the_whole_process_group_and_reports_failure(monkeypatch, tmp_path):
    """The core fix, exercised behaviourally (#14524). Case A of three (see
    `_kill_process_group`'s two siblings below for Case B and C -- review,
    round 2, found and fixed fail-open shapes in those, not this one).

    Spawns a process that (a) ignores SIGTERM and (b) backgrounds a `sleep`
    grandchild -- the shape of a real stuck ansible-playbook run with a
    still-open ssh child. `_run_subprocess` must come back well inside the
    timeout with a FAILED result, and BOTH pids must actually be dead
    afterwards -- not merely that a kill was attempted.

    Discriminates: pre-#14524, `_run_subprocess` has no `timeout_s`
    parameter at all, so this call raises `TypeError` immediately (this test
    fails, fast, not by hanging). Post-fix it passes.

    `ansible_dir=tmp_path` (CI finding): see `test_run_subprocess_without_
    timeout_is_unaffected`'s docstring -- a bare `PlaybookExecutor()`'s
    default `ansible_dir` does not exist on a CI runner, and `cwd=` at spawn
    fails before `timeout_s` is ever reached.
    """
    executor = playbook_executor.PlaybookExecutor(ansible_dir=tmp_path)
    # Short grace period so a SIGTERM-ignoring child escalates to SIGKILL
    # quickly -- this test must not itself take anywhere near the real
    # AUTOBOT_PLAYBOOK_KILL_GRACE_S default (5s) times two signal rounds.
    monkeypatch.setattr(playbook_executor, "PLAYBOOK_KILL_GRACE_S", 0.3)

    parent_pid_file = tmp_path / "parent.pid"
    child_pid_file = tmp_path / "child.pid"

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


def test_kill_process_group_is_a_noop_on_an_already_exited_process():
    """No crash when the timeout races the process exiting on its own."""
    executor = playbook_executor.PlaybookExecutor()

    async def _go():
        process = await asyncio.create_subprocess_exec(
            "/bin/true",
            start_new_session=True,
        )
        await process.wait()
        # Already reaped -- os.killpg(process.pid, sig) now raises ProcessLookupError
        # on the very first signal, since pgid == pid (start_new_session=True) needs
        # no separate lookup that could itself go stale (review round 2, Case B).
        await executor._kill_process_group(process)

    asyncio.run(_go())  # must not raise


def _spawn_group(executor, script: str, pid_dir: Path):
    """Spawn *script* via `_run_subprocess`'s own spawn path and return the process.

    Shared by the Case B/C tests below. Uses `asyncio.create_subprocess_exec`
    directly with `start_new_session=True` -- the same flag `_run_subprocess`
    passes -- so `_kill_process_group` is exercised exactly as it runs in
    production, without also going through the timeout/streaming machinery
    Case A already covers. `pid_dir` is always a fresh `tmp_path`, so unlike
    an earlier version of this helper there is no stale-file cleanup to do.
    """
    return asyncio.create_subprocess_exec(
        "/bin/bash",
        "-c",
        script,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )


async def _read_group_pids(pid_dir: Path) -> tuple[int, int]:
    for _ in range(100):
        if (pid_dir / "leader.pid").exists() and (pid_dir / "sibling.pid").exists():
            break
        await asyncio.sleep(0.03)
    leader_pid = int((pid_dir / "leader.pid").read_text().strip())
    sibling_pid = int((pid_dir / "sibling.pid").read_text().strip())
    return leader_pid, sibling_pid


def test_kill_process_group_handles_a_leader_already_reaped_before_a_sibling_dies(monkeypatch, tmp_path):
    """Case B (#14524 review, round 2): the direct pid is ALREADY GONE when
    `_kill_process_group` is called, while a SIBLING in the same group is
    still alive -- the only way an ATTACHED run wedges after ansible itself
    has exited: a surviving group member still holding the inherited stdout
    pipe open, so `_run_subprocess`'s read side never sees EOF.

    Reproduced deterministically (not raced) by explicitly awaiting
    `process.wait()` -- reaping the leader -- BEFORE calling
    `_kill_process_group`, forcing the exact precondition the old
    `os.getpgid(process.pid)` lookup failed on: it raised
    `ProcessLookupError` and returned, signalling NOTHING, while the sibling
    (`$BASHPID` of the backgrounded subshell -- NOT `$$`, which bash does not
    change inside a subshell) kept running. `pgid = process.pid` (no lookup)
    fixes this: the pgid is known from spawn time regardless of whether the
    leader itself still exists.
    """
    executor = playbook_executor.PlaybookExecutor()
    monkeypatch.setattr(playbook_executor, "PLAYBOOK_KILL_GRACE_S", 0.3)

    # Leader backgrounds a TERM-ignoring subshell, then exits immediately --
    # reaped almost instantly, well before any signal is ever sent to it.
    script = (
        f"echo $$ > {tmp_path}/leader.pid\n"
        f"(trap '' TERM; echo $BASHPID > {tmp_path}/sibling.pid; sleep 30) &\n"
        "disown\n"
        "exit 0\n"
    )

    async def _go():
        process = await _spawn_group(executor, script, tmp_path)
        leader_pid, sibling_pid = await _read_group_pids(tmp_path)
        await process.wait()  # force-reap the leader BEFORE the kill call
        await executor._kill_process_group(process)
        return leader_pid, sibling_pid

    leader_pid, sibling_pid = asyncio.run(_go())
    assert _wait_until_dead(leader_pid, timeout_s=2), "leader was expected to already be reaped"
    assert _wait_until_dead(
        sibling_pid, timeout_s=3
    ), "Case B: a sibling surviving the leader's own exit must still be killed"


def test_kill_process_group_handles_a_leader_dying_on_sigterm_before_a_sibling_does(monkeypatch, tmp_path):
    """Case C (#14524 review, round 2): the direct child dies on the FIRST
    SIGTERM (it does not trap it) while a sibling in the same group ignores
    that same signal and keeps running.

    The OLD SIGTERM/SIGKILL escalation loop awaited `process.wait()` --
    reaping the leader succeeded almost immediately -- and returned believing
    cleanup was done, so SIGKILL was never sent to the survivor (verified
    3/3 in review's own reproduction). The escalation decision now checks the
    WHOLE GROUP (`_process_group_is_dead`, a signal-0 existence probe) after
    reaping the leader, not the one pid `asyncio` tracks.
    """
    executor = playbook_executor.PlaybookExecutor()
    monkeypatch.setattr(playbook_executor, "PLAYBOOK_KILL_GRACE_S", 0.3)

    # Leader does NOT trap TERM (dies on the first signal); its backgrounded
    # subshell DOES, and keeps running until SIGKILL reaches the group.
    script = (
        f"echo $$ > {tmp_path}/leader.pid\n"
        f"(trap '' TERM; echo $BASHPID > {tmp_path}/sibling.pid; sleep 30) &\n"
        "wait\n"
    )

    async def _go():
        process = await _spawn_group(executor, script, tmp_path)
        leader_pid, sibling_pid = await _read_group_pids(tmp_path)
        await executor._kill_process_group(process)
        return leader_pid, sibling_pid

    leader_pid, sibling_pid = asyncio.run(_go())
    assert _wait_until_dead(leader_pid, timeout_s=2)
    assert _wait_until_dead(
        sibling_pid, timeout_s=3
    ), "Case C: a sibling outliving the leader's own SIGTERM death must still get SIGKILL"


def test_run_git_kills_a_hung_git_via_the_process_group(monkeypatch, tmp_path):
    """`_update_code_source`'s own git subcommands, hardened the same way (#14524 round 2).

    A lone `proc.kill()` (the pre-fix shape) reaches only git's own pid; a
    surviving ssh/credential-helper child holding the pipes open would leave
    the un-wrapped retry `communicate()` blocked forever. `_run_git` is
    exercised here against a FAKE `git` on `PATH` (a shell script that
    ignores SIGTERM and backgrounds a sibling) rather than the real binary,
    so the test is deterministic and fast instead of depending on real git's
    own timing -- `_run_git`'s hardcoded target name ("git") is still what
    resolves, only where it resolves TO changes.

    Discriminates: pre-#14524 round 2, `_run_git` had no `start_new_session`
    and killed only the direct pid on timeout -- the fake git's sibling
    would survive. Post-fix both die and `_run_git` returns -1 promptly.
    """
    executor = playbook_executor.PlaybookExecutor()
    monkeypatch.setattr(playbook_executor, "PLAYBOOK_KILL_GRACE_S", 0.3)
    monkeypatch.setattr(playbook_executor, "GIT_COMMAND_TIMEOUT_S", 0.3)

    fake_bin_dir = tmp_path / "fakebin"
    fake_bin_dir.mkdir()
    leader_pid_file = tmp_path / "leader.pid"
    sibling_pid_file = tmp_path / "sibling.pid"
    fake_git = fake_bin_dir / "git"
    fake_git.write_text(
        "#!/bin/bash\n"
        "trap '' TERM\n"
        f"echo $$ > {leader_pid_file}\n"
        f"(trap '' TERM; echo $BASHPID > {sibling_pid_file}; sleep 30) &\n"
        "wait\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)

    monkeypatch.setenv("PATH", f"{fake_bin_dir}:{os.environ.get('PATH', '')}")

    async def _go():
        return await executor._run_git(tmp_path, "fetch", "origin")

    started = time.monotonic()
    returncode = asyncio.run(_go())
    elapsed = time.monotonic() - started

    assert returncode == -1, "a killed git command must report a non-zero, non-crash returncode"
    assert elapsed < 5, f"a timed-out git command must return promptly, took {elapsed:.1f}s"

    for _ in range(100):
        if leader_pid_file.exists() and sibling_pid_file.exists():
            break
        time.sleep(0.02)
    leader_pid = int(leader_pid_file.read_text().strip())
    sibling_pid = int(sibling_pid_file.read_text().strip())
    assert _wait_until_dead(leader_pid, timeout_s=2), "the fake git process itself survived its own timeout"
    assert _wait_until_dead(
        sibling_pid, timeout_s=3
    ), "a surviving child of a killed git command is exactly the orphan this fix exists to prevent"


def _executor_with_fake_code_source(tmp_path: Path) -> "playbook_executor.PlaybookExecutor":
    """A PlaybookExecutor whose code_source_dir (ansible_dir.parent.parent) has a `.git` dir.

    Shared by the _update_code_source return-value tests below -- lets
    `_update_code_source` past its early "no .git -- skipping" return
    (itself always `True`, tested separately) without a real git checkout.
    """
    code_source_dir = tmp_path / "code_source"
    (code_source_dir / ".git").mkdir(parents=True)
    ansible_dir = code_source_dir / "autobot-slm-backend" / "ansible"
    ansible_dir.mkdir(parents=True)
    return playbook_executor.PlaybookExecutor(ansible_dir=ansible_dir)


def test_update_code_source_returns_true_when_no_git_dir_present():
    """Dev-mode / no code_source checkout: nothing to sync is success, not failure."""
    executor = playbook_executor.PlaybookExecutor(ansible_dir=Path("/nonexistent/ansible"))
    assert asyncio.run(executor._update_code_source()) is True


def test_update_code_source_returns_true_when_every_git_step_succeeds(tmp_path):
    """Discriminates against a pre-#14524-round-3 regression: `_update_code_source`
    used to return `None` (discarded at the call site) -- `is True`, not
    merely falsy, proves this is the NEW, real boolean contract.
    """
    executor = _executor_with_fake_code_source(tmp_path)

    async def _ok(*_args, **_kwargs):
        return 0

    async def _noop_log(*_args, **_kwargs):
        return None

    executor._run_git = _ok
    executor._log_updated_head_commit = _noop_log

    assert asyncio.run(executor._update_code_source()) is True


def test_update_code_source_returns_false_when_fetch_fails(tmp_path):
    """`_run_git` returning non-zero for `fetch` must fail the WHOLE sync --
    the pre-round-3 code already `return`ed early here, but discarded that
    at the `execute_playbook` call site. This test covers the return VALUE;
    `test_execute_playbook_refuses_detached_run_on_sync_failure` below covers
    the caller actually using it.
    """
    executor = _executor_with_fake_code_source(tmp_path)

    async def _run_git(_code_source_dir, *args, **_kwargs):
        return 0 if args[0] == "checkout" else 1  # fetch (and reset) fail

    executor._run_git = _run_git

    assert asyncio.run(executor._update_code_source()) is False


def test_update_code_source_returns_false_when_only_checkout_fails(tmp_path):
    """A checkout failure alone does not early-return (fetch/reset still run,
    matching the pre-existing "continuing" log message), but must still make
    the overall result `False` -- the original code tracked this nowhere.
    """
    executor = _executor_with_fake_code_source(tmp_path)

    async def _run_git(_code_source_dir, *args, **_kwargs):
        return 1 if args[0] == "checkout" else 0

    async def _noop_log(*_args, **_kwargs):
        return None

    executor._run_git = _run_git
    executor._log_updated_head_commit = _noop_log

    assert asyncio.run(executor._update_code_source()) is False


def test_execute_playbook_refuses_detached_run_on_sync_failure():
    """The second real defect from review round 2: a failed/timed-out code_source
    sync used to be silently discarded, so `execute_playbook` deployed
    whatever revision code_source held and could return `success: True` --
    a SILENT STALE DEPLOY on the self-update (`detach=True`) path, worse
    than the hang this issue fixes because it is invisible.

    Discriminates: the nonexistent playbook name would raise `FileNotFoundError`
    from the very next line if execution reached it -- this test asserts it
    does NOT (the sync-failure return fires first), which fails loudly
    (wrong exception, not silently) against pre-round-3 code, where
    `_update_code_source`'s result was discarded and this early return did
    not exist at all.
    """
    executor = playbook_executor.PlaybookExecutor()

    async def _sync_failed():
        return False

    executor._update_code_source = _sync_failed

    result = asyncio.run(executor.execute_playbook("definitely-does-not-exist.yml", detach=True))

    assert result["success"] is False
    assert result["timed_out"] is False
    assert "sync failed" in result["output"]


def test_execute_playbook_continues_non_detached_despite_sync_failure():
    """The ordinary per-role/per-node restart path must keep its original
    best-effort behaviour -- `manage-service.yml` barely depends on
    code_source being current, and refusing every restart because of a
    transient git hiccup would be a regression in the other direction.

    Discriminates the ATTACHED-path branch specifically: proven by reaching
    the FileNotFoundError the very next line raises, rather than the
    sync-failure dict the detached branch returns instead.
    """
    executor = playbook_executor.PlaybookExecutor()

    async def _sync_failed():
        return False

    executor._update_code_source = _sync_failed

    try:
        asyncio.run(executor.execute_playbook("definitely-does-not-exist.yml", detach=False))
        raised = False
    except FileNotFoundError:
        raised = True

    assert raised, "a non-detached run must still proceed past a sync failure to the playbook-exists check"
