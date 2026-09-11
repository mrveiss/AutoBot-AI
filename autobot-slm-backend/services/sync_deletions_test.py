# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services/sync_deletions.py (#16310).

A normal code-sync must remove, from the deployed tree, every path git proves
was tracked at the previously-deployed commit and deleted or renamed away at
the new one -- and must never touch a path git has never tracked. Exercised
against a real, disposable git repository (not a mock): the guarantee this
module makes is specifically about what ``git diff --diff-filter=DR`` says,
so the fixture has to be real git history, not a stand-in for it.

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
    "services.sync_deletions",
)
_prev_modules = {name: sys.modules.get(name) for name in _SWAPPED}
try:
    _real_load("services.deploy_artifacts", _SERVICES_DIR / "deploy_artifacts.py")
    _dc = _real_load("services.drift_checker", _SERVICES_DIR / "drift_checker.py")
    _real_load("services.deployed_dir_resolver", _SERVICES_DIR / "deployed_dir_resolver.py")
    _real_load("services.git_subprocess", _SERVICES_DIR / "git_subprocess.py")
    _sd = _real_load("services.sync_deletions", _SERVICES_DIR / "sync_deletions.py")
finally:
    for _name, _prev in _prev_modules.items():
        if _prev is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prev

remove_deleted_paths = _sd.remove_deleted_paths
cleanup_colocated_components = _sd.cleanup_colocated_components
DEPLOYED_COMMIT_MARKER = _sd.DEPLOYED_COMMIT_MARKER
_remove_npu_workers_leftover = _sd._remove_npu_workers_leftover


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


def _write_marker(deployed_dir: Path, commit: str) -> None:
    (deployed_dir / DEPLOYED_COMMIT_MARKER).write_text(f"{commit}\n", encoding="utf-8")


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
    marker_text = await asyncio.to_thread((deployed / DEPLOYED_COMMIT_MARKER).read_text, encoding="utf-8")
    assert marker_text.strip() == commit_b


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
    commit_b = _commit_all(repo, "no-op")  # nothing changes; distinct HEAD not required

    deployed = tmp_path / "deployed"
    _write(deployed / "keep.py")
    _write(deployed / "host_state.env")  # never tracked in the fixture repo at all
    _write_marker(deployed, commit_a)

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
    # No .deployed_commit marker written -- previous commit is unknown.

    result = await remove_deleted_paths("comp", str(repo / "comp"), str(deployed), repo_root=str(repo))

    assert result.removed == []
    assert (deployed / "gone.py").exists()
    assert result.skipped_reason is not None
    assert not (deployed / DEPLOYED_COMMIT_MARKER).exists(), "no baseline was known -- nothing recorded either"


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
# The nested npu_workers.yaml leftover (AC3)
# ---------------------------------------------------------------------------


def test_npu_workers_leftover_removed_only_while_byte_identical(tmp_path) -> None:
    backend = tmp_path / "autobot-backend"
    canonical = backend / "config" / "npu_workers.yaml"
    _write(canonical, "workers: []\n")
    nested = backend / "autobot-backend" / "config" / "npu_workers.yaml"
    _write(nested, "workers: []\n")

    line = _remove_npu_workers_leftover(str(backend))

    assert line is not None and "removed" in line
    assert not nested.exists()
    assert canonical.exists(), "the canonical file must never be touched"


def test_npu_workers_leftover_left_alone_when_it_differs(tmp_path) -> None:
    backend = tmp_path / "autobot-backend"
    canonical = backend / "config" / "npu_workers.yaml"
    _write(canonical, "workers: []\n")
    nested = backend / "autobot-backend" / "config" / "npu_workers.yaml"
    _write(nested, "workers: [{id: 1}]\n")  # differs -- must survive

    line = _remove_npu_workers_leftover(str(backend))

    assert line is None
    assert nested.exists(), "no-data-loss: only a byte-identical duplicate may be removed"


# ---------------------------------------------------------------------------
# cleanup_colocated_components: skips a component not deployed on this host
# ---------------------------------------------------------------------------


async def test_cleanup_skips_a_component_not_colocated_on_this_host(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_sd, "get_live_dir", lambda component: str(tmp_path / "never-created" / component))

    lines = await cleanup_colocated_components(components=frozenset({"autobot-backend"}))

    assert lines == []


async def test_cleanup_reports_removed_paths_for_a_colocated_component(tmp_path, monkeypatch) -> None:
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

    logged: list[str] = []
    lines = await cleanup_colocated_components(components=frozenset({"autobot-backend"}), log=logged.append)

    assert any("gone.py" in line for line in lines)
    assert logged == lines
    assert not (deployed / "gone.py").exists()
