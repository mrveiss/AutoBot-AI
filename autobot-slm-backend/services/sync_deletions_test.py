# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services/sync_deletions.py (#16310).

A normal code-sync must remove, from the deployed tree, every path git proves
was tracked at the previously-deployed commit and deleted or renamed away at
the new one -- and must never touch a path git has never tracked, kept-on-disk
host state, or a path a symlink would resolve outside the deployed tree.
Exercised against a real, disposable git repository (not a mock): several of
these guarantees are specifically claims about what git itself says
(``diff --diff-filter=DR``, ``check-ignore``), which a mock cannot stand in
for.

Bootstrap mirrors services/deployed_dir_resolver_test.py: the root conftest
stubs services.drift_checker/deployed_dir_resolver/git_tracker/sync_deletions
as MagicMocks (AST-derived from api/code_sync.py's imports), so all of them
are real-loaded here, in dependency order, before this module's own imports
run.
"""

from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
import types
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

_SERVICES_DIR = Path(__file__).parent

# Stub services.git_tracker with just what drift_checker/sync_deletions read
# at module scope -- DEFAULT_REPO_PATH -- so their real loads succeed without
# pulling in git_tracker's own SQLAlchemy/config dependencies.
_gt_stub = types.ModuleType("services.git_tracker")
_gt_stub.DEFAULT_REPO_PATH = "/opt/autobot/code_source"  # type: ignore[attr-defined]
sys.modules["services.git_tracker"] = _gt_stub


def _real_load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_SWAPPED = (
    "services.deploy_artifacts",
    "services.drift_checker",
    "services.deployed_dir_resolver",
    "services.git_subprocess",
    "services.host_state_filter",
    "services.marker_io",
    "services.sync_deletions",
)
_prev_modules = {name: sys.modules.get(name) for name in _SWAPPED}
try:
    _real_load("services.deploy_artifacts", _SERVICES_DIR / "deploy_artifacts.py")
    _dc = _real_load("services.drift_checker", _SERVICES_DIR / "drift_checker.py")
    _real_load("services.deployed_dir_resolver", _SERVICES_DIR / "deployed_dir_resolver.py")
    _real_load("services.git_subprocess", _SERVICES_DIR / "git_subprocess.py")
    _real_load("services.host_state_filter", _SERVICES_DIR / "host_state_filter.py")
    _real_load("services.marker_io", _SERVICES_DIR / "marker_io.py")
    _sd = _real_load("services.sync_deletions", _SERVICES_DIR / "sync_deletions.py")
finally:
    for _name, _prev in _prev_modules.items():
        if _prev is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prev

remove_deleted_paths = _sd.remove_deleted_paths
apply_role_deletions = _sd.apply_role_deletions
remove_npu_workers_leftover = _sd.remove_npu_workers_leftover
DELETION_MARKER = _sd.DELETION_MARKER
_LEGACY_BOOTSTRAP_MARKER = _sd._LEGACY_BOOTSTRAP_MARKER


# ---------------------------------------------------------------------------
# Fixture git repo helpers
# ---------------------------------------------------------------------------

_GIT_ENV = {
    **scrubbed_git_env(),
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@e",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@e",
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, env=_GIT_ENV, capture_output=True, text=True)
    return result.stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, env=_GIT_ENV)


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_marker(deployed_dir: Path, commit: str, name: str = DELETION_MARKER) -> None:
    (deployed_dir / name).write_text(f"{commit}\n", encoding="utf-8")


async def _read_marker_text(path: Path) -> str:
    return (await asyncio.to_thread(path.read_text, encoding="utf-8")).strip()


# ---------------------------------------------------------------------------
# AC1 / #16310's fixture-repo test list
# ---------------------------------------------------------------------------


async def test_a_deleted_file_is_removed_from_the_deployed_tree(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    _write(repo / "comp" / "gone.py")
    commit_a = _commit_all(repo, "seed")

    (repo / "comp" / "gone.py").unlink()
    commit_b = _commit_all(repo, "delete gone.py")

    deployed = tmp_path / "deployed"
    _write(deployed / "keep.py")
    _write(deployed / "gone.py")
    _write_marker(deployed, commit_a)

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.removed == ["gone.py"]
    assert not (deployed / "gone.py").exists()
    assert (deployed / "keep.py").exists()
    assert result.previous_commit == commit_a
    assert result.new_commit == commit_b
    assert await _read_marker_text(deployed / DELETION_MARKER) == commit_b


async def test_a_renamed_files_old_path_is_removed(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "old.py", "content")
    commit_a = _commit_all(repo, "seed")

    _git(repo, "mv", "comp/old.py", "comp/new.py")
    commit_b = _commit_all(repo, "rename old.py to new.py")

    deployed = tmp_path / "deployed"
    _write(deployed / "old.py", "content")
    _write_marker(deployed, commit_a)

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.removed == ["old.py"]
    assert not (deployed / "old.py").exists()
    assert result.new_commit == commit_b


async def test_a_never_tracked_file_survives(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    commit_a = _commit_all(repo, "seed")

    deployed = tmp_path / "deployed"
    _write(deployed / "keep.py")
    _write(deployed / "host_state.env")  # never tracked in the fixture repo at all
    _write_marker(deployed, commit_a)
    _commit_all(repo, "no-op")

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.removed == []
    assert (deployed / "host_state.env").exists(), "a path git never tracked must never be touched"


async def test_unknown_previous_commit_means_no_deletion(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "gone.py")
    _commit_all(repo, "seed")
    (repo / "comp" / "gone.py").unlink()
    _commit_all(repo, "delete gone.py")

    deployed = tmp_path / "deployed"
    _write(deployed / "gone.py")
    # No marker written at all (dedicated or legacy) -- previous commit is unknown.

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.removed == []
    assert (deployed / "gone.py").exists()
    assert result.skipped_reason is not None
    assert not (deployed / DELETION_MARKER).exists(), "no baseline was known -- nothing recorded either"


async def test_same_commit_is_a_no_op(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    commit_a = _commit_all(repo, "seed")

    deployed = tmp_path / "deployed"
    _write(deployed / "keep.py")
    _write_marker(deployed, commit_a)

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.removed == []
    assert result.previous_commit == commit_a
    assert result.new_commit == commit_a


# ---------------------------------------------------------------------------
# #16310 review, BLOCKING 1: marker collision with the SLM self-update (#12202)
# ---------------------------------------------------------------------------


async def test_never_writes_the_legacy_deployed_commit_marker(tmp_path) -> None:
    """``.deployed_commit`` is ``_get_slm_deployed_commit()``'s C4 skip-gate --
    this module must only ever write its OWN dedicated marker."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "gone.py")
    commit_a = _commit_all(repo, "seed")
    (repo / "comp" / "gone.py").unlink()
    _commit_all(repo, "delete gone.py")

    deployed = tmp_path / "deployed"
    _write(deployed / "gone.py")
    _write_marker(deployed, commit_a)

    await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert not (deployed / _LEGACY_BOOTSTRAP_MARKER).exists()


async def test_bootstraps_from_the_legacy_marker_when_its_own_is_absent(tmp_path) -> None:
    """First run under this feature: the dedicated marker is absent, so the
    legacy ``.deployed_commit`` (written by something else, e.g. ansible) is
    READ as the baseline -- catching already-known stale files -- but never
    written back to."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "gone.py")
    commit_a = _commit_all(repo, "seed")
    (repo / "comp" / "gone.py").unlink()
    commit_b = _commit_all(repo, "delete gone.py")

    deployed = tmp_path / "deployed"
    _write(deployed / "gone.py")
    _write_marker(deployed, commit_a, name=_LEGACY_BOOTSTRAP_MARKER)

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.removed == ["gone.py"]
    assert await _read_marker_text(deployed / DELETION_MARKER) == commit_b
    legacy_text = await _read_marker_text(deployed / _LEGACY_BOOTSTRAP_MARKER)
    assert legacy_text == commit_a, "the legacy marker must be read, never overwritten"


async def test_own_marker_wins_over_the_legacy_one_once_it_exists(tmp_path) -> None:
    """Once this module has run once, its own marker is authoritative -- a
    stale legacy marker must not resurrect an old baseline."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    commit_a = _commit_all(repo, "seed")
    commit_b = _commit_all(repo, "no-op")

    deployed = tmp_path / "deployed"
    _write(deployed / "keep.py")
    _write_marker(deployed, commit_b)  # own marker: already caught up
    _write_marker(deployed, commit_a, name=_LEGACY_BOOTSTRAP_MARKER)  # legacy: stale

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.previous_commit == commit_b


# ---------------------------------------------------------------------------
# #16310 review, BLOCKING 2: untracked-but-kept host state (#16300's pattern)
# ---------------------------------------------------------------------------


async def test_a_git_rm_cached_then_gitignored_file_survives(tmp_path) -> None:
    """Tracked, then `git rm --cached`, then added to .gitignore, then kept on
    disk: git still shows it as a `D` between commits, but it must survive."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "secrets.local.yaml", "token: abc\n")
    commit_a = _commit_all(repo, "seed")

    _git(repo, "rm", "--cached", "-q", "comp/secrets.local.yaml")
    _write(repo / "comp" / ".gitignore", "secrets.local.yaml\n")
    commit_b = _commit_all(repo, "untrack and ignore secrets.local.yaml")

    deployed = tmp_path / "deployed"
    _write(deployed / "secrets.local.yaml", "token: abc\n")
    _write_marker(deployed, commit_a)

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.removed == [], "a gitignored, kept-on-disk file must never be deleted"
    assert (deployed / "secrets.local.yaml").exists()
    assert "secrets.local.yaml" in result.kept
    assert result.new_commit == commit_b


async def test_a_host_state_excludes_match_survives_even_without_gitignore(tmp_path) -> None:
    """`data/` is protected by HOST_STATE_EXCLUDES independent of .gitignore --
    covers a file that git shows deleted (never ignored) but rsync itself
    would never have deleted either."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "data" / "runtime.db")
    commit_a = _commit_all(repo, "seed")
    (repo / "comp" / "data" / "runtime.db").unlink()
    _commit_all(repo, "delete data/runtime.db from source")

    deployed = tmp_path / "deployed"
    _write(deployed / "data" / "runtime.db")
    _write_marker(deployed, commit_a)

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.removed == []
    assert "data/runtime.db" in result.kept
    assert (deployed / "data" / "runtime.db").exists()


# ---------------------------------------------------------------------------
# #16310 review, MEDIUM 3: symlink containment
# ---------------------------------------------------------------------------


async def test_a_path_through_a_symlinked_parent_outside_deployed_dir_is_refused(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "escape" / "payload.txt")
    commit_a = _commit_all(repo, "seed")
    (repo / "comp" / "escape" / "payload.txt").unlink()
    _commit_all(repo, "delete escape/payload.txt")

    outside = tmp_path / "outside"
    outside.mkdir()
    canary = outside / "payload.txt"
    _write(canary, "do not delete me")

    deployed = tmp_path / "deployed"
    deployed.mkdir()
    (deployed / "escape").symlink_to(outside)  # deployed/escape -> ../outside
    _write_marker(deployed, commit_a)

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.removed == [], "a path resolving outside deployed_dir must never be unlinked"
    assert canary.exists(), "the file outside the deployed tree must survive"


# ---------------------------------------------------------------------------
# The nested npu_workers.yaml leftover (AC3)
# ---------------------------------------------------------------------------


def test_npu_workers_leftover_removed_only_while_byte_identical(tmp_path) -> None:
    backend = tmp_path / "autobot-backend"
    canonical = backend / "config" / "npu_workers.yaml"
    _write(canonical, "workers: []\n")
    nested = backend / "autobot-backend" / "config" / "npu_workers.yaml"
    _write(nested, "workers: []\n")

    line = remove_npu_workers_leftover(str(backend))

    assert line is not None and "removed" in line
    assert not nested.exists()
    assert canonical.exists(), "the canonical file must never be touched"


def test_npu_workers_leftover_left_alone_when_it_differs(tmp_path) -> None:
    backend = tmp_path / "autobot-backend"
    canonical = backend / "config" / "npu_workers.yaml"
    _write(canonical, "workers: []\n")
    nested = backend / "autobot-backend" / "config" / "npu_workers.yaml"
    _write(nested, "workers: [{id: 1}]\n")  # differs -- must survive

    line = remove_npu_workers_leftover(str(backend))

    assert line is None
    assert nested.exists(), "no-data-loss: only a byte-identical duplicate may be removed"


# ---------------------------------------------------------------------------
# apply_role_deletions: the co-located-role integration point
# ---------------------------------------------------------------------------


async def test_apply_role_deletions_skips_a_role_with_no_component_mapping(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_sd, "get_live_dir", lambda component: str(tmp_path / "deployed" / component))

    lines = await apply_role_deletions("monitoring")  # no ALLOWED_COMPONENTS counterpart

    assert lines == []


async def test_apply_role_deletions_skips_a_component_not_colocated_here(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_sd, "get_live_dir", lambda component: str(tmp_path / "never-created" / component))

    lines = await apply_role_deletions("backend")

    assert lines == []


async def test_apply_role_deletions_reports_removed_paths_for_backend(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "autobot-backend" / "gone.py")
    commit_a = _commit_all(repo, "seed")
    (repo / "autobot-backend" / "gone.py").unlink()
    _commit_all(repo, "delete gone.py")

    deployed = tmp_path / "deployed" / "autobot-backend"
    _write(deployed / "gone.py")
    _write_marker(deployed, commit_a)

    monkeypatch.setattr(_sd, "get_live_dir", lambda component: str(tmp_path / "deployed" / component))
    monkeypatch.setattr(_sd, "get_default_source_dir", lambda component: str(repo / component))
    monkeypatch.setattr(_sd, "remove_deleted_paths", lambda *a, **kw: remove_deleted_paths(*a, repo_root=str(repo)))

    lines = await apply_role_deletions("backend")

    assert any("gone.py" in line for line in lines)
    assert not (deployed / "gone.py").exists()
