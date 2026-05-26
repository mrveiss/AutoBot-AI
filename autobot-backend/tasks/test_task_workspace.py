# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for services/task_workspace.py (GH#6471).

Two scenarios:
  1. Two agents on different tasks → two distinct worktrees, no shared state.
  2. Heartbeat resume → allocate() is idempotent; same workspace_dir returned.

Uses a real git repository in a temp directory so actual git worktree
operations are exercised end-to-end.

Placement note: the services/ directory has conftest stubs that break pytest
fixture resolution for ALL tests in that directory; we live in tasks/ instead.
The module is loaded via importlib.util so we bypass the services package stub.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest


def _load_tw():
    """Load task_workspace directly, bypassing the services package stub."""
    src = Path(__file__).resolve().parent.parent / "services" / "task_workspace.py"
    spec = importlib.util.spec_from_file_location("_task_workspace_direct", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_tw = _load_tw()
allocate = _tw.allocate
release = _tw.release
cleanup_stale = _tw.cleanup_stale


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Initialise a minimal git repo in tmp_path with one initial commit."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (tmp_path / "README.md").write_text("test repo")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return tmp_path


class TestTwoAgentsTwoDifferentTasks:
    """Two agents on different tasks must get distinct, isolated worktrees (GH#6471)."""

    def test_distinct_worktree_paths(self, git_repo: Path) -> None:
        task_a = "aaaaaaaa-0000-0000-0000-000000000001"
        task_b = "bbbbbbbb-0000-0000-0000-000000000002"

        ws_a = allocate(task_a, "agent-x", repo_root=git_repo)
        ws_b = allocate(task_b, "agent-y", repo_root=git_repo)

        assert ws_a.worktree_path != ws_b.worktree_path
        assert Path(ws_a.worktree_path).exists()
        assert Path(ws_b.worktree_path).exists()

    def test_no_shared_state(self, git_repo: Path) -> None:
        task_a = "aaaaaaaa-0000-0000-0000-000000000003"
        task_b = "bbbbbbbb-0000-0000-0000-000000000004"

        ws_a = allocate(task_a, "agent-x", repo_root=git_repo)
        ws_b = allocate(task_b, "agent-y", repo_root=git_repo)

        (Path(ws_a.worktree_path) / "agent_x_work.txt").write_text("agent-x result")

        assert not (Path(ws_b.worktree_path) / "agent_x_work.txt").exists()

    def test_both_are_new_allocations(self, git_repo: Path) -> None:
        task_a = "aaaaaaaa-0000-0000-0000-000000000005"
        task_b = "bbbbbbbb-0000-0000-0000-000000000006"

        ws_a = allocate(task_a, "agent-x", repo_root=git_repo)
        ws_b = allocate(task_b, "agent-y", repo_root=git_repo)

        assert ws_a.is_new is True
        assert ws_b.is_new is True
        assert ws_a.branch != ws_b.branch


class TestHeartbeatResume:
    """Subsequent allocate() for the same task must resume the same worktree (GH#6471)."""

    def test_same_worktree_on_second_call(self, git_repo: Path) -> None:
        task_id = "cccccccc-0000-0000-0000-000000000001"

        first = allocate(task_id, "agent-resume", repo_root=git_repo)
        second = allocate(task_id, "agent-resume", repo_root=git_repo)

        assert first.worktree_path == second.worktree_path

    def test_resume_returns_is_new_false(self, git_repo: Path) -> None:
        task_id = "cccccccc-0000-0000-0000-000000000002"

        allocate(task_id, "agent-resume", repo_root=git_repo)
        resumed = allocate(task_id, "agent-resume", repo_root=git_repo)

        assert resumed.is_new is False

    def test_workspace_dir_stable_across_heartbeats(self, git_repo: Path) -> None:
        task_id = "cccccccc-0000-0000-0000-000000000003"

        ws1 = allocate(task_id, "agent-resume", repo_root=git_repo)
        wt = Path(ws1.worktree_path)
        (wt / "heartbeat_1.txt").write_text("tick 1")
        subprocess.run(["git", "-C", str(wt), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-m", "hb1"],
            check=True,
            capture_output=True,
        )

        ws2 = allocate(task_id, "agent-resume", repo_root=git_repo)

        assert ws2.worktree_path == ws1.worktree_path
        assert (Path(ws2.worktree_path) / "heartbeat_1.txt").exists()

    def test_metadata_preserved_on_resume(self, git_repo: Path) -> None:
        task_id = "cccccccc-0000-0000-0000-000000000004"

        ws1 = allocate(task_id, "agent-resume", repo_root=git_repo)
        ws2 = allocate(task_id, "agent-resume", repo_root=git_repo)

        assert ws2.created_at == ws1.created_at
        assert ws2.branch == ws1.branch

    @pytest.mark.parametrize(
        "bad_id",
        [
            "../../etc/passwd",
            "../secret",
            "task/../../foo",
            "a" * 129,
            "",
            "foo bar",
            "foo\x00bar",
        ],
    )
    def test_allocate_rejects_traversal_task_ids(self, git_repo: Path, bad_id: str) -> None:
        """Path traversal and malformed task_ids must raise ValueError (GH#6471 blocker 2)."""
        with pytest.raises(ValueError, match="Invalid task_id"):
            allocate(bad_id, "agent-sec", repo_root=git_repo)

    @pytest.mark.parametrize(
        "bad_id",
        [
            "../../etc/passwd",
            "../worktrees",
        ],
    )
    def test_release_rejects_traversal_task_ids(self, git_repo: Path, bad_id: str) -> None:
        with pytest.raises(ValueError, match="Invalid task_id"):
            release(bad_id, repo_root=git_repo)


class TestActiveLock:
    """active-lock file prevents eviction of running worktrees (MVA-1154)."""

    def test_allocate_writes_lock_file(self, git_repo: Path) -> None:
        task_id = "eeeeeee0-0000-0000-0000-000000000001"
        ws = allocate(task_id, "agent-lock", repo_root=git_repo)
        assert (Path(ws.worktree_path) / ".active-lock").exists()

    def test_resume_refreshes_lock_file(self, git_repo: Path) -> None:
        task_id = "eeeeeee0-0000-0000-0000-000000000002"
        ws = allocate(task_id, "agent-lock", repo_root=git_repo)
        lock_file = Path(ws.worktree_path) / ".active-lock"
        lock_file.unlink()
        assert not lock_file.exists()
        allocate(task_id, "agent-lock", repo_root=git_repo)
        assert lock_file.exists()

    def test_release_removes_entire_workspace(self, git_repo: Path) -> None:
        task_id = "eeeeeee0-0000-0000-0000-000000000003"
        ws = allocate(task_id, "agent-lock", repo_root=git_repo)
        assert (Path(ws.worktree_path) / ".active-lock").exists()
        release(task_id, repo_root=git_repo)
        assert not Path(ws.worktree_path).exists()

    def test_enforce_limit_skips_locked_evicts_unlocked(self, git_repo: Path) -> None:
        old_task = "eeeeeee0-0000-0000-0000-000000000010"
        active_task = "eeeeeee0-0000-0000-0000-000000000011"
        new_task = "eeeeeee0-0000-0000-0000-000000000012"

        ws_old = allocate(old_task, "agent-evict", repo_root=git_repo, max_per_agent=2)
        ws_active = allocate(active_task, "agent-evict", repo_root=git_repo, max_per_agent=2)

        # Simulate ws_old's subprocess finishing without calling release()
        (Path(ws_old.worktree_path) / ".active-lock").unlink()

        # Third allocation must evict the unlocked ws_old, not the locked ws_active
        allocate(new_task, "agent-evict", repo_root=git_repo, max_per_agent=2)

        assert not Path(ws_old.worktree_path).exists(), "unlocked worktree must be evicted"
        assert Path(ws_active.worktree_path).exists(), "locked active worktree must be preserved"

    def test_enforce_limit_preserves_all_locked_worktrees(self, git_repo: Path) -> None:
        task_a = "eeeeeee0-0000-0000-0000-000000000020"
        task_b = "eeeeeee0-0000-0000-0000-000000000021"
        task_c = "eeeeeee0-0000-0000-0000-000000000022"

        ws_a = allocate(task_a, "agent-noevict", repo_root=git_repo, max_per_agent=2)
        ws_b = allocate(task_b, "agent-noevict", repo_root=git_repo, max_per_agent=2)
        # Both locked; _enforce_limit finds no eviction candidates — all survive
        ws_c = allocate(task_c, "agent-noevict", repo_root=git_repo, max_per_agent=2)

        assert Path(ws_a.worktree_path).exists(), "locked worktree A must not be evicted"
        assert Path(ws_b.worktree_path).exists(), "locked worktree B must not be evicted"
        assert Path(ws_c.worktree_path).exists(), "new worktree C must exist"

    def test_cleanup_stale_skips_locked_worktree(self, git_repo: Path) -> None:
        import json as _json

        task_id = "eeeeeee0-0000-0000-0000-000000000030"
        ws = allocate(task_id, "agent-stale", repo_root=git_repo)
        workspace_dir = Path(ws.worktree_path)

        # Backdate metadata so the worktree looks ancient
        meta_file = workspace_dir / ".workspace-meta.json"
        meta = _json.loads(meta_file.read_text())
        meta["created_at"] = "2000-01-01T00:00:00+00:00"
        meta_file.write_text(_json.dumps(meta))

        # Lock is still present — stale cleanup must skip this worktree
        cleaned = cleanup_stale(max_age_days=0, repo_root=git_repo)

        assert task_id not in cleaned
        assert workspace_dir.exists()
