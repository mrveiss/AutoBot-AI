#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The installed `pre-push` must converge on its tracked copy (#17578).

Hooks are **copied, not symlinked** (#11598), and nothing kept
`.git/hooks/pre-push` in step with `tools/git-hooks/pre-push`. Measured on a
live checkout before this landed: the installed copy was the tracked file as of
`4bae334f12` — two revisions behind, missing #16912's two `could_not_run`
branches and #17035's `REPO_ROOT="$PWD"`.

The second one is why this is not housekeeping. The old spelling resolves
through `git rev-parse --show-toplevel`, which an inherited `GIT_DIR` outranks,
so the running hook could `cd` into a **different checkout** and verify files
that were not the ones being pushed. Every "hooks green" claim made while that
was installed described a gate nobody could name.

`post-checkout` and `post-merge` now both ask the installer to sync it, because
between them they cover how a session actually meets a new hook version —
`worktree add`, a branch switch, a pull. Neither fires for a session that only
commits and pushes on one branch, which is the gap the one-off installer run
closes and which no hook can.

Driven in a throwaway repo, the way `hook_self_sync_atomic_test.py` drives the
self-sync: *"Asserted on behaviour, not on source text. A grep for `cp` would
pass on a hook that had stopped self-syncing altogether."*
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = repo_root()
_INSTALLER = REPO_ROOT / "scripts" / "install-git-hooks.sh"
_TRACKED_PREPUSH = REPO_ROOT / "tools" / "git-hooks" / "pre-push"

#: A hook that is ours but stale: it carries the marker the installer uses to
#: tell "managed by us" from "a developer's own", so it is replaced rather than
#: backed up. The realistic drift case.
_STALE_MANAGED = "#!/usr/bin/env bash\n# AutoBot pre-push, two revisions ago\nexit 0\n"

#: A hook the installer must NOT destroy: no AutoBot marker, so it is somebody's
#: own file and gets moved aside first.
_UNMANAGED = "#!/usr/bin/env bash\n# my own hook\nexit 0\n"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """#15246: env scrubbed — an inherited GIT_DIR would aim these calls,
    `checkout` included, at the real repository instead of tmp_path.
    """
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False, env=scrubbed_git_env())


def _seed(tmp_path: Path) -> Path:
    """A throwaway repo carrying the three real files this behaviour needs."""
    repo = tmp_path / "repo"
    (repo / "scripts" / "hooks").mkdir(parents=True)
    (repo / "tools" / "git-hooks").mkdir(parents=True)
    _git(tmp_path, "init", "--quiet", "--initial-branch=main", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")

    for src, dest in (
        (_INSTALLER, repo / "scripts" / "install-git-hooks.sh"),
        (REPO_ROOT / "scripts" / "hooks" / "post-checkout", repo / "scripts" / "hooks" / "post-checkout"),
        (REPO_ROOT / "scripts" / "hooks" / "post-merge", repo / "scripts" / "hooks" / "post-merge"),
        (_TRACKED_PREPUSH, repo / "tools" / "git-hooks" / "pre-push"),
    ):
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        dest.chmod(0o755)

    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "seed")
    _git(repo, "branch", "other")
    return repo


def _install_hook(repo: Path, name: str, text: str) -> Path:
    """Put *text* in place as the live hook, the way a stale copy sits there."""
    live = repo / ".git" / "hooks" / name
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text(text, encoding="utf-8")
    live.chmod(0o755)
    return live


def _wire_event_hook(repo: Path, name: str) -> None:
    """Install the real post-checkout / post-merge as the live hook."""
    live = repo / ".git" / "hooks" / name
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text((repo / "scripts" / "hooks" / name).read_text(encoding="utf-8"), encoding="utf-8")
    live.chmod(0o755)


def _tracked_text() -> str:
    return _TRACKED_PREPUSH.read_text(encoding="utf-8")


class TestTheEventHooksConverge:
    """The two events that are how a session meets a new hook version."""

    def test_a_checkout_replaces_a_stale_pre_push(self, tmp_path: Path) -> None:
        repo = _seed(tmp_path)
        _wire_event_hook(repo, "post-checkout")
        live = _install_hook(repo, "pre-push", _STALE_MANAGED)

        _git(repo, "checkout", "other")

        assert live.read_text(encoding="utf-8") == _tracked_text()

    def test_a_merge_replaces_a_stale_pre_push(self, tmp_path: Path) -> None:
        """post-merge, because post-checkout never fires for a session that
        stays on its branch and pulls -- `scripts/hooks/post-merge` states that
        firing rule itself (#16934)."""
        repo = _seed(tmp_path)
        _wire_event_hook(repo, "post-merge")
        live = _install_hook(repo, "pre-push", _STALE_MANAGED)

        # A merge that lands something, so the hook runs.
        _git(repo, "checkout", "other")
        (repo / "other.txt").write_text("x\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "--quiet", "-m", "other")
        _git(repo, "checkout", "main")
        _install_hook(repo, "pre-push", _STALE_MANAGED)  # the checkout above may have synced it
        _git(repo, "merge", "--no-ff", "--no-edit", "other")

        assert live.read_text(encoding="utf-8") == _tracked_text()

    def test_a_missing_pre_push_is_installed_not_skipped(self, tmp_path: Path) -> None:
        """A fresh clone has no hook at all -- absent must converge too."""
        repo = _seed(tmp_path)
        _wire_event_hook(repo, "post-checkout")
        live = repo / ".git" / "hooks" / "pre-push"

        _git(repo, "checkout", "other")

        assert live.is_file()
        assert live.read_text(encoding="utf-8") == _tracked_text()

    def test_the_installed_hook_is_executable(self, tmp_path: Path) -> None:
        """Present-but-not-executable is the same as absent, and quieter."""
        repo = _seed(tmp_path)
        _wire_event_hook(repo, "post-checkout")
        live = _install_hook(repo, "pre-push", _STALE_MANAGED)

        _git(repo, "checkout", "other")

        assert live.stat().st_mode & 0o111


class TestWhatTheSyncMustNotDo:
    """Three properties that make this safe to run on every checkout."""

    def test_an_unmanaged_hook_is_moved_aside_not_destroyed(self, tmp_path: Path) -> None:
        """Somebody's own pre-push is not ours to delete.

        The installer's existing rule: a hook with no `AutoBot` marker is backed
        up before the template replaces it.
        """
        repo = _seed(tmp_path)
        _wire_event_hook(repo, "post-checkout")
        _install_hook(repo, "pre-push", _UNMANAGED)

        _git(repo, "checkout", "other")

        backups = list((repo / ".git" / "hooks").glob("pre-push.bak.*"))
        assert backups, "the developer's own hook was replaced with no backup"
        assert backups[0].read_text(encoding="utf-8") == _UNMANAGED

    def test_the_sync_does_not_touch_core_hooks_path(self, tmp_path: Path) -> None:
        """Unsetting core.hooksPath is a config mutation, and a checkout is not
        the moment to make one behind the operator's back. A full installer run
        still normalises it; `--sync` must not."""
        repo = _seed(tmp_path)
        _git(repo, "config", "--local", "core.hooksPath", ".git/hooks")

        subprocess.run(
            ["bash", "scripts/install-git-hooks.sh", "--sync", "pre-push"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            env={**scrubbed_git_env(), "HOOKS_DEST": str(repo / ".git" / "hooks")},
        )

        configured = _git(repo, "config", "--local", "--get-all", "core.hooksPath").stdout.strip()
        assert configured == ".git/hooks", "the sync unset core.hooksPath"

    def test_it_is_silent_when_the_hook_is_already_current(self, tmp_path: Path) -> None:
        """A hook that prints on every checkout is one the third person disables."""
        repo = _seed(tmp_path)
        _install_hook(repo, "pre-push", _tracked_text())

        completed = subprocess.run(
            ["bash", "scripts/install-git-hooks.sh", "--sync", "pre-push"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            env={**scrubbed_git_env(), "HOOKS_DEST": str(repo / ".git" / "hooks")},
        )

        assert completed.returncode == 0
        assert completed.stdout.strip() == "", completed.stdout
        assert completed.stderr.strip() == "", completed.stderr

    def test_a_replacement_is_reported_even_though_the_mode_is_quiet(self, tmp_path: Path) -> None:
        """The other half of quiet: silence about a change would make this fix
        invisible in the opposite direction -- drift corrected with nobody told
        the gate had been wrong."""
        repo = _seed(tmp_path)
        _install_hook(repo, "pre-push", _STALE_MANAGED)

        completed = subprocess.run(
            ["bash", "scripts/install-git-hooks.sh", "--sync", "pre-push"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            env={**scrubbed_git_env(), "HOOKS_DEST": str(repo / ".git" / "hooks")},
        )

        assert "pre-push" in completed.stdout


class TestTheSyncModeItself:
    """`--sync` is narrow on purpose."""

    def test_a_name_that_is_not_managed_fails_loudly(self, tmp_path: Path) -> None:
        """Syncing nothing reads exactly like a clean sync, so a typo must not."""
        repo = _seed(tmp_path)

        completed = subprocess.run(
            ["bash", "scripts/install-git-hooks.sh", "--sync", "pre-pushh"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            env={**scrubbed_git_env(), "HOOKS_DEST": str(repo / ".git" / "hooks")},
        )

        assert completed.returncode == 2
        assert "not one of" in completed.stderr

    def test_sync_with_no_names_fails(self, tmp_path: Path) -> None:
        repo = _seed(tmp_path)

        completed = subprocess.run(
            ["bash", "scripts/install-git-hooks.sh", "--sync"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            env={**scrubbed_git_env(), "HOOKS_DEST": str(repo / ".git" / "hooks")},
        )

        assert completed.returncode == 2

    @pytest.mark.parametrize("hook", ["post-checkout", "post-merge"])
    def test_both_event_hooks_ask_for_pre_push_only(self, hook: str) -> None:
        """`pre-commit` is already kept in step by post-checkout's own
        flock-aware comparison. A second mechanism over one file is how two
        managers drift, and it would strip the flock that step re-injects.

        Source-level on purpose: the behavioural tests above prove the sync
        works, and this pins the SCOPE, which behaviour cannot distinguish from
        the other mechanism doing the same job.
        """
        text = (REPO_ROOT / "scripts" / "hooks" / hook).read_text(encoding="utf-8")
        assert "--sync pre-push" in text
        assert "--sync pre-commit" not in text
        assert "--sync commit-msg" not in text


class TestTheVersionSkewBetweenHookAndInstaller:
    """`.git/hooks` is ONE directory; the installer is per worktree (#17578).

    So a hook installed from a tree that has `--sync` is invoked from trees that
    do not. Before the probe, an installer without the mode ignored the unknown
    argument, ran `main "$@"`, and performed a FULL install -- including
    `normalise_hooks_path`, the config mutation `--sync` exists to avoid. That
    happened on this machine: a merge in one worktree installed another branch's
    unmerged hooks for every session.

    Both directions are closed: the hook probes before calling, and the installer
    refuses an unknown option instead of falling through.
    """

    @staticmethod
    def _installer_without_the_mode(repo: Path) -> None:
        """Replace the installer with one that does not know `--sync`."""
        target = repo / "scripts" / "install-git-hooks.sh"
        text = target.read_text(encoding="utf-8").replace("SYNC_ONLY=", "LEGACY_NO_SYNC_HERE=")
        assert "SYNC_ONLY=" not in text
        target.write_text(text, encoding="utf-8")
        target.chmod(0o755)

    def test_a_hook_does_not_call_an_installer_without_the_mode(self, tmp_path: Path) -> None:
        repo = _seed(tmp_path)
        _wire_event_hook(repo, "post-checkout")
        self._installer_without_the_mode(repo)
        _git(repo, "add", "-A")
        _git(repo, "commit", "--quiet", "-m", "legacy installer")
        # `other` was branched BEFORE that commit, and post-checkout runs AFTER
        # the working tree is updated -- so without this the hook would read the
        # checked-out branch's ORIGINAL installer, the probe would pass, and the
        # test would fail for a reason that has nothing to do with the skew.
        _git(repo, "branch", "--force", "other", "main")
        live = _install_hook(repo, "pre-push", _STALE_MANAGED)

        completed = _git(repo, "checkout", "other")
        output = completed.stdout + completed.stderr

        # Not synced, and -- the point -- no full install either.
        assert live.read_text(encoding="utf-8") == _STALE_MANAGED
        assert "done." not in output, f"a full install ran: {output}"
        assert "installed commit-msg" not in output

    def test_an_unknown_option_fails_instead_of_installing_everything(self, tmp_path: Path) -> None:
        """The other direction: a future flag must not silently become a full run."""
        repo = _seed(tmp_path)

        completed = subprocess.run(
            ["bash", "scripts/install-git-hooks.sh", "--frobnicate"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            env={**scrubbed_git_env(), "HOOKS_DEST": str(repo / ".git" / "hooks")},
        )

        assert completed.returncode == 2
        assert "unknown option" in completed.stderr
        assert not (repo / ".git" / "hooks" / "commit-msg").exists(), "a rejected run still installed hooks"


class TestProvenance:
    """Say which pre-push is in place, so nobody has to ask afterwards.

    Four sessions cited "hooks green" today against an installed hook none of
    them could name, and establishing which one had run took a history walk over
    the tracked file hashing each revision. `git hash-object` is the identity git
    itself uses, so the installed and tracked sides are directly comparable.
    """

    def test_a_replacement_names_the_new_and_old_identities(self, tmp_path: Path) -> None:
        repo = _seed(tmp_path)
        _wire_event_hook(repo, "post-checkout")
        _install_hook(repo, "pre-push", _STALE_MANAGED)

        completed = _git(repo, "checkout", "other")
        output = completed.stdout + completed.stderr

        assert "pre-push now" in output, output
        assert "tracked" in output

    def test_nothing_is_said_when_the_hook_was_already_current(self, tmp_path: Path) -> None:
        """Provenance on every checkout would be noise; on a change it is the record."""
        repo = _seed(tmp_path)
        _wire_event_hook(repo, "post-checkout")
        _install_hook(repo, "pre-push", _tracked_text())

        completed = _git(repo, "checkout", "other")

        assert "pre-push now" not in (completed.stdout + completed.stderr)
