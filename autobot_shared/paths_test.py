"""Tests for canonical project-root resolution (#13149)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from autobot_shared.paths import (
    BASE_DIR_ENV,
    PROJECT_ROOT_ENV,
    ProjectRootUndeterminable,
    is_checkout_root,
    project_root,
    resolve_project_root,
    scrubbed_git_env,
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

    def test_honours_an_explicit_base_dir_override(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv(PROJECT_ROOT_ENV, raising=False)
        monkeypatch.setenv(BASE_DIR_ENV, "/srv/autobot-test")

        bare = tmp_path / "bare"
        bare.mkdir()

        assert resolve_project_root(bare / "mod.py") == Path("/srv/autobot-test")


class TestUndeterminableRoot:
    """#14544: no silent guess — an unplaceable root is a raise, not a path.

    The pre-#14544 last resort returned a hardcoded ``/opt/autobot`` here,
    which is exactly the "defaults to the live install" defect this module
    exists to close one layer up in every ``sys.path`` bootstrap that calls
    it. On a real checkout or a real install this branch is never reached —
    step 1 or step 2 always resolves first — so raising costs nothing there.
    """

    def test_raises_when_nothing_identifies_the_root(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv(PROJECT_ROOT_ENV, raising=False)
        monkeypatch.delenv(BASE_DIR_ENV, raising=False)

        bare = tmp_path / "bare"
        bare.mkdir()

        with pytest.raises(ProjectRootUndeterminable):
            resolve_project_root(bare / "mod.py")

    def test_the_raise_names_both_overrides(self, tmp_path, monkeypatch) -> None:
        """The message must tell the caller what to set, not just that it failed."""
        monkeypatch.delenv(PROJECT_ROOT_ENV, raising=False)
        monkeypatch.delenv(BASE_DIR_ENV, raising=False)

        bare = tmp_path / "bare"
        bare.mkdir()

        with pytest.raises(ProjectRootUndeterminable) as excinfo:
            resolve_project_root(bare / "mod.py")

        assert PROJECT_ROOT_ENV in str(excinfo.value)
        assert BASE_DIR_ENV in str(excinfo.value)


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


class TestRealGitWorktree:
    """#13357: the resolver run from inside a REAL ``git worktree``.

    ``TestWorktreeBoundary`` above builds a directory that *looks* like a
    worktree and calls :func:`resolve_project_root` with a path it chose. That
    proves the walk's shape, but it cannot catch #13357, because the fixture
    supplies the very answer under test: nothing in it is a real worktree,
    ``project_root()`` itself is never called, and ``.git`` is a file only
    because the fixture wrote one.

    This test instead creates an actual repository, adds an actual worktree,
    copies the real ``paths.py`` into it, and runs ``project_root()`` in a
    **subprocess** whose ``__file__`` is inside the worktree. The answer comes
    from git's own on-disk layout, so a regression to the pre-#13357 two-pass
    walk (all ancestors for ``.env``, then all ancestors for the markers) fails
    here: the worktree has no ``.env`` of its own, so that walk climbs to the
    main tree's and returns the wrong checkout.
    """

    #: Reads the resolver from a given directory and prints only its answer.
    PROBE = (
        "import importlib.util, pathlib, sys\n"
        "spec = importlib.util.spec_from_file_location('probe_paths', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "print(module.project_root())\n"
    )

    @staticmethod
    def _git(*args: str, cwd: Path) -> None:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            # scrubbed_git_env, not os.environ: the pre-push hook runs this
            # suite with GIT_DIR pointing at the worktree it is pushing, and
            # `git init`/`git commit` in *this* fixture then operate on that
            # repository instead of the temporary one. Both tests in this class
            # failed that way from a worktree, which is every checkout here
            # (#15176).
            env={
                **scrubbed_git_env(),
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_SYSTEM": "/dev/null",
            },
        )

    def _build_main_tree(self, tmp_path: Path) -> Path:
        """A real git repository shaped like this one: package dir, tracked file, untracked .env."""
        main = tmp_path / "main"
        (main / "autobot_shared").mkdir(parents=True)
        shutil.copy(Path(__file__).with_name("paths.py"), main / "autobot_shared" / "paths.py")
        (main / ".gitignore").write_text(".env\n.worktrees/\n", encoding="utf-8")

        self._git("init", "-b", "main", cwd=main)
        self._git("config", "user.email", "test@example.invalid", cwd=main)
        self._git("config", "user.name", "test", cwd=main)
        self._git("add", "-A", cwd=main)
        self._git("commit", "-m", "initial", cwd=main)

        # The condition that makes #13357 possible: .env exists ONLY in the main
        # tree. It is git-ignored, so `git worktree add` cannot reproduce it.
        (main / ".env").write_text("AUTOBOT_MARKER=main-tree\n", encoding="utf-8")
        return main

    def _resolve_from(self, directory: Path) -> Path:
        """Run ``project_root()`` against the ``paths.py`` living under *directory*."""
        env = {k: v for k, v in os.environ.items() if k not in (PROJECT_ROOT_ENV, BASE_DIR_ENV)}
        completed = subprocess.run(
            [sys.executable, "-c", self.PROBE, str(directory / "autobot_shared" / "paths.py")],
            cwd=directory,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return Path(completed.stdout.strip())

    def test_resolves_to_the_worktree_not_the_main_checkout(self, tmp_path) -> None:
        main = self._build_main_tree(tmp_path)
        worktree = main / ".worktrees" / "issue-1"
        self._git("worktree", "add", str(worktree), "-b", "issue-1", cwd=main)

        # Preconditions, asserted rather than assumed — if git ever started
        # copying .env into worktrees, or writing .git as a directory, this
        # test would pass while testing nothing.
        assert (worktree / ".git").is_file(), "a worktree's .git must be a file, not a directory"
        assert not (worktree / ".env").exists(), "the worktree must not carry its own .env"
        assert (main / ".env").is_file(), "the main tree must carry the .env that the walk can escape to"

        resolved = self._resolve_from(worktree)

        assert resolved == worktree.resolve(), f"resolved to {resolved}, expected the worktree root"
        assert resolved != main.resolve(), "resolver escaped the worktree and returned the main checkout"

    def test_the_main_checkout_still_resolves_to_itself(self, tmp_path) -> None:
        """The control: the same probe in the main tree must answer the main tree.

        Without this, a resolver that simply returned ``Path.cwd()`` — or the
        probe's own directory — would satisfy the assertion above for entirely
        the wrong reason.
        """
        main = self._build_main_tree(tmp_path)

        assert self._resolve_from(main) == main.resolve()
