"""Tests for canonical project-root resolution (#13149)."""

from __future__ import annotations

from pathlib import Path

from autobot_shared.paths import (
    PROJECT_ROOT_ENV,
    is_checkout_root,
    project_root,
    resolve_project_root,
)


def _make_checkout(root: Path) -> Path:
    """Build a directory that satisfies both checkout markers."""
    (root / "autobot_shared").mkdir(parents=True)
    (root / ".git").mkdir()
    return root


class TestExplicitEnvironment:
    """AUTOBOT_PROJECT_ROOT outranks every form of inference."""

    def test_env_var_wins(self, tmp_path, monkeypatch) -> None:
        checkout = _make_checkout(tmp_path / "checkout")
        override = tmp_path / "elsewhere"
        override.mkdir()
        monkeypatch.setenv(PROJECT_ROOT_ENV, str(override))

        assert resolve_project_root(checkout / "pkg" / "mod.py") == override

    def test_unset_env_falls_through_to_the_walk(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv(PROJECT_ROOT_ENV, raising=False)
        checkout = _make_checkout(tmp_path / "checkout")

        assert resolve_project_root(checkout / "pkg" / "mod.py") == checkout


class TestWorktreeBoundary:
    """A checkout root stops the walk — the regression this module was written for.

    Worktrees live at ``<main-tree>/.worktrees/<name>/`` and are git-ignored, so
    they carry no ``.env``. A two-pass walk (every ancestor for ``.env``, then
    every ancestor for the markers) escaped the worktree and matched the main
    tree's ``.env``, resolving every worktree to the wrong checkout.
    """

    def test_worktree_does_not_escape_to_the_main_tree(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv(PROJECT_ROOT_ENV, raising=False)

        main = _make_checkout(tmp_path / "main")
        (main / ".env").write_text("X=1\n", encoding="utf-8")

        # A worktree: both markers (.git is a FILE here), and deliberately no .env.
        worktree = tmp_path / "main" / ".worktrees" / "issue-1"
        (worktree / "autobot_shared").mkdir(parents=True)
        (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        assert not (worktree / ".env").exists()

        resolved = resolve_project_root(worktree / "autobot_shared" / "mod.py")

        assert resolved == worktree, "worktree escaped to the main tree"
        assert resolved != main


class TestDeployedInstall:
    """The case that must still be caught: a configured install has no .git."""

    def test_env_file_matches_without_checkout_markers(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv(PROJECT_ROOT_ENV, raising=False)

        install = tmp_path / "opt" / "autobot"
        (install / "autobot_shared").mkdir(parents=True)
        (install / ".env").write_text("X=1\n", encoding="utf-8")
        assert not (install / ".git").exists()

        assert resolve_project_root(install / "autobot_shared" / "mod.py") == install

    def test_nearest_ancestor_wins_over_a_higher_one(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv(PROJECT_ROOT_ENV, raising=False)

        outer = _make_checkout(tmp_path / "outer")
        inner = _make_checkout(tmp_path / "outer" / "nested")

        assert resolve_project_root(inner / "pkg" / "mod.py") == inner
        assert inner != outer

    def test_falls_back_to_the_install_location(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv(PROJECT_ROOT_ENV, raising=False)
        monkeypatch.setenv("AUTOBOT_BASE_DIR", "/srv/autobot-test")

        bare = tmp_path / "bare"
        bare.mkdir()

        assert resolve_project_root(bare / "mod.py") == Path("/srv/autobot-test")


class TestCheckoutMarkers:
    """Both markers are required; ``.git`` may be a file."""

    def test_clone_and_worktree_both_recognised(self, tmp_path) -> None:
        clone = _make_checkout(tmp_path / "clone")

        worktree = tmp_path / "worktree"
        (worktree / "autobot_shared").mkdir(parents=True)
        (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")

        assert is_checkout_root(clone) is True
        assert is_checkout_root(worktree) is True

    def test_either_marker_alone_is_insufficient(self, tmp_path) -> None:
        git_only = tmp_path / "other-repo"
        (git_only / ".git").mkdir(parents=True)
        pkg_only = tmp_path / "vendored"
        (pkg_only / "autobot_shared").mkdir(parents=True)

        assert is_checkout_root(git_only) is False
        assert is_checkout_root(pkg_only) is False


class TestLiveResolution:
    """The cached entry point resolves this very checkout."""

    def test_resolves_to_a_real_directory_holding_this_package(self) -> None:
        root = project_root()

        assert root.exists()
        assert (root / "autobot_shared" / "paths.py").exists()
