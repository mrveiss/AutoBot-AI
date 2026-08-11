# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Duplicate-scan cancellation, single-flight and traversal pruning (#12779).

`asyncio.wait_for` cancels the AWAIT, but work already running in a
ThreadPoolExecutor cannot be cancelled. So every 120 s timeout returned None to
the caller while the worker thread kept walking the whole tree, and each
subsequent poll queued ANOTHER full scan. Abandoned threads accumulated until
they saturated CPU and pushed RSS 2.8 -> 7.0 GB, at which point /api/health
stopped answering and the GUI reported "Backend API Unreachable" for a process
that was alive throughout.

Compounding it, the scan globbed the entire tree once PER EXTENSION and applied
the skip-list only after descending — so node_modules/, .git/ and venv/ were
fully walked and then discarded, N times over.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from api.codebase_analytics.duplicate_detector import DuplicateCodeDetector


def _tree(root: Path) -> None:
    """Build a source tree with excluded dirs that must never be descended."""
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "real.py").write_text("x = 1\n", encoding="utf-8")
    # #13602: `.worktrees` and `.claude/worktrees` were NOT in SKIP_DIRS, despite
    # _get_files_to_scan's own docstring claiming `.worktrees/` was pruned. On a
    # real checkout that was 160,105 of 167,072 code files — the repo scanned ~26
    # times over. This test passed throughout, because _tree() never built one.
    (root / ".claude" / "worktrees" / "wt2" / "pkg").mkdir(parents=True)
    (root / ".claude" / "worktrees" / "wt2" / "pkg" / "noise.py").write_text("z = 3\n", encoding="utf-8")
    for skipped in ("node_modules", ".git", "venv", ".worktrees"):
        deep = root / skipped / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "noise.py").write_text("y = 2\n", encoding="utf-8")


class TestTraversalPruning:
    def test_excluded_directories_are_not_scanned(self, tmp_path):
        _tree(tmp_path)
        found = DuplicateCodeDetector(project_root=str(tmp_path))._get_files_to_scan()
        names = {p.name for p in found}
        assert "real.py" in names
        assert "noise.py" not in names, "excluded trees must not contribute files"

    def test_excluded_directories_are_never_descended(self, tmp_path, monkeypatch):
        """Pruning must happen BEFORE descent, not by filtering afterwards.

        The old implementation walked node_modules/.git/venv fully and then threw
        the results away — which is what made a single scan expensive enough to
        blow the timeout. Assert os.walk is never handed those directories.
        """
        _tree(tmp_path)
        import api.codebase_analytics.duplicate_detector as det

        visited: list[str] = []
        real_walk = det.os.walk

        def _tracking_walk(top, *a, **kw):
            for dirpath, dirnames, filenames in real_walk(top, *a, **kw):
                visited.append(str(dirpath))
                yield dirpath, dirnames, filenames

        monkeypatch.setattr(det.os, "walk", _tracking_walk)
        DuplicateCodeDetector(project_root=str(tmp_path))._get_files_to_scan()

        for excluded in ("node_modules", ".git", "venv"):
            assert not any(excluded in v for v in visited), f"descended into {excluded}"

    def test_tree_is_walked_once_not_once_per_extension(self, tmp_path, monkeypatch):
        """The old code called glob() once per extension over the whole tree."""
        _tree(tmp_path)
        import api.codebase_analytics.duplicate_detector as det

        calls = {"n": 0}
        real_walk = det.os.walk

        def _counting_walk(top, *a, **kw):
            calls["n"] += 1
            yield from real_walk(top, *a, **kw)

        monkeypatch.setattr(det.os, "walk", _counting_walk)
        d = DuplicateCodeDetector(project_root=str(tmp_path))
        assert len(d.code_extensions) > 1, "fixture assumes multiple extensions"
        d._get_files_to_scan()
        assert calls["n"] == 1, f"tree walked {calls['n']} times, expected 1"


class TestCooperativeCancellation:
    def test_pre_set_token_stops_the_scan_immediately(self, tmp_path):
        """A timed-out scan must stop, not run to completion for a discarded result."""
        _tree(tmp_path)
        token = threading.Event()
        token.set()
        d = DuplicateCodeDetector(project_root=str(tmp_path), cancel_token=token)
        assert d._get_files_to_scan() == []

    def test_scan_completes_normally_without_a_token(self, tmp_path):
        """Cancellation must be opt-in — the default path is unchanged."""
        _tree(tmp_path)
        d = DuplicateCodeDetector(project_root=str(tmp_path))
        assert d._cancel_token is None
        assert d._cancelled() is False
        assert [p.name for p in d._get_files_to_scan()] == ["real.py"]

    def test_unset_token_does_not_cancel(self, tmp_path):
        _tree(tmp_path)
        d = DuplicateCodeDetector(project_root=str(tmp_path), cancel_token=threading.Event())
        assert d._cancelled() is False
        assert [p.name for p in d._get_files_to_scan()] == ["real.py"]


class TestSingleFlight:
    """Concurrent polls must not each queue a full tree walk."""

    @pytest.mark.asyncio
    async def test_second_concurrent_scan_is_refused(self, monkeypatch):
        import api.codebase_analytics.endpoints.duplicates as ep

        monkeypatch.setattr(ep, "_duplicate_scan_lock", threading.Lock())
        assert ep._duplicate_scan_lock.acquire(blocking=False)
        try:
            # Lock already held => a second caller must bail out rather than
            # start another walk. This is the accumulation the issue reported.
            result = await ep._run_duplicate_analysis("/tmp", 0.5, False)
            assert result is None
        finally:
            ep._duplicate_scan_lock.release()

    def test_lock_is_released_for_the_next_caller(self, monkeypatch):
        import api.codebase_analytics.endpoints.duplicates as ep

        monkeypatch.setattr(ep, "_duplicate_scan_lock", threading.Lock())
        assert ep._duplicate_scan_lock.acquire(blocking=False)
        ep._duplicate_scan_lock.release()
        assert ep._duplicate_scan_lock.acquire(blocking=False)
        ep._duplicate_scan_lock.release()


class TestScanRootInsideASkippedDirectory:
    """#13602: adding `.worktrees` to SKIP_DIRS arms a trap.

    Five call sites tested `SKIP_DIRS & set(path.parts)` on an ABSOLUTE path,
    which asks whether a skip name appears anywhere in it — including in the
    scan root. CI and development both run from inside `.worktrees/`, so the
    moment the name was added, scanning from such a root would classify every
    file below it as skippable and report an empty codebase. No error, no log,
    just zero results — indistinguishable from a clean repo.

    The root-relative check (#7128b's pattern) is what makes the name safe to
    add at all.
    """

    def test_a_root_inside_worktrees_still_finds_its_own_files(self, tmp_path):
        root = tmp_path / ".worktrees" / "issue-13602"
        _tree(root)
        found = DuplicateCodeDetector(project_root=str(root))._get_files_to_scan()
        names = {p.name for p in found}
        assert "real.py" in names, "a scan rooted inside .worktrees must not erase itself"
        assert "noise.py" not in names, "nested skip dirs must still be pruned"

    def test_should_skip_path_is_relative_to_the_scan_root(self, tmp_path):
        """The dead method wired in (#13602). It had no callers, so its absolute
        comparison was a trap armed for whoever wired it in next."""
        root = tmp_path / ".worktrees" / "issue-13602"
        (root / "pkg").mkdir(parents=True)
        detector = DuplicateCodeDetector(project_root=str(root))

        assert not detector._should_skip_path(root / "pkg" / "real.py")
        assert detector._should_skip_path(root / ".worktrees" / "nested" / "x.py")
        assert detector._should_skip_path(root / "node_modules" / "y.py")
