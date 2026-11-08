# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The reach base tree is shared per commit, never a registered worktree, and clean on SIGTERM (#20875)."""

from __future__ import annotations

import logging
import multiprocessing
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from repo_tests import _reach_base
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="flock and SIGTERM")


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(_reach_base.CACHE_DIR_ENV, str(tmp_path / "cache"))
    monkeypatch.setattr(_reach_base, "_TREE", {})
    monkeypatch.setattr(_reach_base, "base_commit", lambda _root: _head())
    return tmp_path / "cache"


def _head() -> str:
    out = subprocess.run(
        ["git", "-C", str(repo_root()), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    return out.stdout.strip()


def _worktrees() -> str:
    out = subprocess.run(
        ["git", "-C", str(repo_root()), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    return out.stdout


def _worker(cache_dir: str, queue: "multiprocessing.Queue[str]") -> None:
    os.environ[_reach_base.CACHE_DIR_ENV] = cache_dir
    _reach_base.base_commit = lambda _root: _head()  # type: ignore[assignment]
    queue.put(str(_reach_base.base_tree()))


def test_concurrent_workers_produce_one_tree(cache: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    procs = [ctx.Process(target=_worker, args=(str(cache), queue)) for _ in range(4)]
    for proc in procs:
        proc.start()
    paths = {queue.get(timeout=300) for _ in procs}
    for proc in procs:
        proc.join(timeout=60)
    trees = [p for p in cache.iterdir() if p.name.startswith(_reach_base.TREE_PREFIX)]
    assert len(paths) == 1 and len(trees) == 1
    assert not [p for p in cache.iterdir() if p.name.startswith(".partial-")]


def test_the_tree_is_not_a_registered_worktree(cache: Path) -> None:
    tree = _reach_base.base_tree()
    assert (tree / "pytest.ini").is_file()
    assert tree.name not in _worktrees() and (tree / ".git").is_dir()


def test_a_second_call_for_the_same_commit_reuses_the_tree(cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = _reach_base.base_tree()
    monkeypatch.setattr(_reach_base, "_TREE", {})
    monkeypatch.setattr(_reach_base, "_extract", lambda *_a: pytest.fail("rebuilt an existing tree"))
    assert _reach_base.base_tree() == first


def test_a_tree_in_an_older_layout_is_rebuilt_not_reused(cache: Path) -> None:
    legacy = cache / f"{_reach_base.TREE_PREFIX}{_head()}"  # the layout before the format was versioned
    legacy.mkdir(parents=True)
    tree = _reach_base.base_tree()
    assert tree != legacy and (tree / ".git").is_dir()


_SLOW_BUILD = """
import os, sys, time
from pathlib import Path
from repo_tests import _reach_base
os.environ[_reach_base.CACHE_DIR_ENV] = sys.argv[1]
_reach_base.base_commit = lambda _root: "{sha}"
def slow(sha, into):
    (into / "half").write_text("x")
    Path(sys.argv[2]).write_text("building")
    time.sleep(60)
_reach_base._extract = slow
_reach_base.base_tree()
"""


def test_sigterm_during_a_build_leaves_no_partial_dir(tmp_path: Path) -> None:
    ready, cache = tmp_path / "ready", tmp_path / "cache"
    script = textwrap.dedent(_SLOW_BUILD).format(sha=_head())
    proc = subprocess.Popen([sys.executable, "-c", script, str(cache), str(ready)], cwd=repo_root())
    for _ in range(300):
        if ready.exists() or proc.poll() is not None:
            break
        time.sleep(0.1)
    assert ready.exists(), "the build never started"
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=30) == -signal.SIGTERM  # default behaviour re-raised
    assert [p.name for p in cache.iterdir() if p.name != ".lock"] == []


def test_a_sigterm_handler_installed_from_c_is_restored_as_the_default(
    cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``signal.signal`` reports a C-installed handler as None; restoring None would raise TypeError."""
    real_signal, original = signal.signal, signal.getsignal(signal.SIGTERM)

    def c_installed(signum: int, handler: object) -> object:
        previous = real_signal(signum, handler)
        return None if handler is _reach_base._on_sigterm else previous

    monkeypatch.setattr(signal, "signal", c_installed)
    try:
        _reach_base.base_tree()
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    finally:
        real_signal(signal.SIGTERM, signal.SIG_DFL if original is None else original)


def test_one_unremovable_stale_tree_is_logged_and_the_prune_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    stale_at = time.time() - _reach_base._STALE_AFTER_S - 60
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        os.utime(tmp_path / name, (stale_at, stale_at))
    (tmp_path / "keep").mkdir()
    real_rmtree, calls = shutil.rmtree, []

    def first_fails(path: Path, *args: object, **kwargs: object) -> None:
        calls.append(Path(path))
        if len(calls) == 1:
            raise PermissionError(13, "Permission denied", str(path))
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(_reach_base.shutil, "rmtree", first_fails)
    with caplog.at_level(logging.WARNING):
        _reach_base._prune(tmp_path, keep=tmp_path / "keep")
    failed, pruned = calls
    assert failed.is_dir() and not pruned.exists() and (tmp_path / "keep").is_dir()
    assert str(failed) in caplog.text and "Permission denied" in caplog.text
