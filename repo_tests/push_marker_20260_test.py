# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20260: a push in its gate holds a remote marker, and the auto-sync leaves that branch alone."""

from __future__ import annotations

import fcntl
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from repo_tests._paths import repo_root

_ROOT = repo_root()
_HOOK = (_ROOT / "tools/git-hooks/pre-push").read_text(encoding="utf-8")
sys.path.insert(0, str(_ROOT / "pipeline-scripts"))
import branch_sync  # noqa: E402
import branch_sync_core as core  # noqa: E402

_ZERO = "0" * 40


def _line(branch: str, expiry: object) -> str:
    return f"abc\t{core.PUSH_MARKER_PREFIX}{branch}/{expiry}"


def test_a_live_marker_holds_its_branch_and_an_expired_one_does_not() -> None:
    listed = "\n".join([_line("issue-1-a", 200), _line("issue-2/with-slash", 200), _line("issue-3-old", 50)])
    assert core.branches_being_pushed(listed, now=100) == {"issue-1-a", "issue-2/with-slash"}


def test_contrast_nothing_listed_or_unparseable_holds_nothing() -> None:
    assert core.branches_being_pushed("", now=100) == set()
    assert core.branches_being_pushed(_line("issue-1-a", "soon"), now=100) == set()
    assert core.branches_being_pushed("abc\trefs/heads/issue-1/200", now=100) == set()


class _Syncer:
    def __init__(self, *_args) -> None:
        self.synced: list[str] = []

    def sync(self, target) -> tuple[str, str]:
        _Syncer.seen.append(target.branch)
        return core.SYNCED, ""


def _run(monkeypatch, being_pushed: set) -> dict:
    _Syncer.seen = []
    pull = {
        "number": 1,
        "created_at": "2026-01-01",
        "head": {"ref": "issue-1-a", "sha": "abc", "repo": {"full_name": "o/r"}},
        "base": {"ref": "main"},
    }
    monkeypatch.setattr(branch_sync, "Syncer", _Syncer)
    git = type(
        "G", (), {"branches": lambda s: ["issue-1-a"], "being_pushed": lambda s: being_pushed, "out": lambda s, *a: ""}
    )()
    gh = type("H", (), {"repo": "o/r", "open_pulls": lambda s: [pull]})()
    return branch_sync.run(git, gh, "main", dry_run=False)


def test_the_bot_skips_a_branch_being_pushed(monkeypatch) -> None:
    results = _run(monkeypatch, {"issue-1-a"})
    assert _Syncer.seen == [] and results[core.PUSH_IN_PROGRESS]


def test_contrast_the_bot_syncs_any_other_branch(monkeypatch) -> None:
    results = _run(monkeypatch, {"issue-2-other"})
    assert _Syncer.seen == ["issue-1-a"] and core.PUSH_IN_PROGRESS not in results


def _fn(name: str) -> str:
    return re.search(rf"^{name}\(\) \{{\n(?:.*\n)*?\}}$", _HOOK, re.MULTILINE).group(0)


def _hook(tmp_path: Path, body: str, gh_exit: int = 0) -> tuple[subprocess.CompletedProcess, str]:
    """The real functions, against a fake gh that logs its arguments."""
    log = tmp_path / "gh.log"
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "gh").write_text(f'#!/bin/bash\necho "$*" >> {log}\nexit {gh_exit}\n', encoding="utf-8")
    (fake / "gh").chmod(0o755)
    script = (
        f'ZERO={_ZERO}; MAX_BUDGET=600; PUSH_MARKER_FILE=$(mktemp); warn() {{ echo "WARN $*"; }}\n'
        f'{_fn("push_marker_api")}\n{_fn("push_marker_clear")}\n{_fn("push_marker_set")}\n{body}\n'
    )
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "AUTOBOT_PUSH_MARKER": "1"}
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, cwd=tmp_path, check=False)
    return done, log.read_text(encoding="utf-8") if log.exists() else ""


def test_the_hook_sets_a_marker_then_clears_it(tmp_path: Path) -> None:
    done, calls = _hook(tmp_path, "push_marker_set issue-1-a abc; push_marker_clear")
    assert done.returncode == 0, done.stderr
    created = re.search(r"-X POST \S+ -f ref=refs/(push-gate/issue-1-a/\d+) -f sha=abc", calls)
    assert created, calls
    assert f"-X DELETE repos/{{owner}}/{{repo}}/git/refs/{created.group(1)}" in calls


def test_a_new_branch_sets_no_marker(tmp_path: Path) -> None:
    _, calls = _hook(tmp_path, f"push_marker_set issue-1-a {_ZERO}")
    assert calls == ""


def test_a_marker_that_cannot_be_written_warns_and_never_blocks(tmp_path: Path) -> None:
    done, _ = _hook(tmp_path, "push_marker_set issue-1-a abc; echo CARRIED-ON", gh_exit=1)
    assert "WARN could not mark" in done.stdout and "CARRIED-ON" in done.stdout


def test_a_marker_set_in_a_stage_subshell_is_cleared_by_the_parent(tmp_path: Path) -> None:
    """A marker written from a subshell is still cleared at exit."""
    _, calls = _hook(tmp_path, "(push_marker_set issue-1-a abc); push_marker_clear")
    created = re.search(r"ref=refs/(push-gate/issue-1-a/\d+)", calls)
    assert created and f"git/refs/{created.group(1)}" in calls.split("-X POST")[1]


def test_queueing_renews_the_marker(tmp_path: Path) -> None:
    """The real wait against a held slot: having waited, it sets a fresh marker for this branch."""
    held = os.open(tmp_path / "slot-1", os.O_CREAT | os.O_WRONLY, 0o600)
    fcntl.flock(held, fcntl.LOCK_EX)
    threading.Timer(1.5, os.close, (held,)).start()
    body = (
        f"{_fn('machine_slot_wait')}\nlog() {{ :; }}\nunset CI AUTOBOT_MACHINE_SLOT_HELD\n"
        f"export AUTOBOT_MACHINE_SLOT_DIR={tmp_path} AUTOBOT_MACHINE_SLOTS=1 AUTOBOT_MACHINE_SLOT_POLL=0.2\n"
        "branch_name=issue-1-a; remote_sha=abc; machine_slot_wait\n"
    )
    done, calls = _hook(tmp_path, body)
    assert done.returncode == 0, done.stderr
    assert "ref=refs/push-gate/issue-1-a/" in calls


def test_contrast_no_wait_means_no_extra_network_call(tmp_path: Path) -> None:
    body = (
        f"{_fn('machine_slot_wait')}\nlog() {{ :; }}\nunset CI AUTOBOT_MACHINE_SLOT_HELD\n"
        f"export AUTOBOT_MACHINE_SLOT_DIR={tmp_path} AUTOBOT_MACHINE_SLOTS=1\n"
        "branch_name=issue-1-a; remote_sha=abc; machine_slot_wait\n"
    )
    _, calls = _hook(tmp_path, body)
    assert calls == ""
