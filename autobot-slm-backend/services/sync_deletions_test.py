# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services/sync_deletions.py (#16310).

Owner decision (#16310): this module only PLANS deletions (git-diff or
bootstrap, filtered by host state / gitignore / lexical containment).
Deletion itself happens ansible-side; nothing here touches a filesystem. The
old and new commit are always supplied by the caller (ansible slurps the
target's marker, or the caller passes both directly) -- there is no marker
I/O left in this module to test.

Exercised against a real, disposable git repository, not a mock: several of
these guarantees are specifically claims about what git itself says
(``diff --diff-filter=DR``, ``log``, ``cat-file -e``, ``check-ignore``).

Bootstrap mirrors services/deployed_dir_resolver_test.py: the root conftest
stubs services.drift_checker/deployed_dir_resolver/git_tracker/sync_deletions
as MagicMocks (AST-derived from api/code_sync.py's imports -- gone now that
code_sync.py no longer imports this module, but the pattern is harmless to
keep for isolation from any other stub state a shared test run left behind).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

_SERVICES_DIR = Path(__file__).parent

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
    "services.sync_deletions",
)
_prev_modules = {name: sys.modules.get(name) for name in _SWAPPED}
try:
    _real_load("services.deploy_artifacts", _SERVICES_DIR / "deploy_artifacts.py")
    _real_load("services.drift_checker", _SERVICES_DIR / "drift_checker.py")
    _real_load("services.deployed_dir_resolver", _SERVICES_DIR / "deployed_dir_resolver.py")
    _real_load("services.git_subprocess", _SERVICES_DIR / "git_subprocess.py")
    _real_load("services.host_state_filter", _SERVICES_DIR / "host_state_filter.py")
    _sd = _real_load("services.sync_deletions", _SERVICES_DIR / "sync_deletions.py")
finally:
    for _name, _prev in _prev_modules.items():
        if _prev is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prev

compute_deletion_plan = _sd.compute_deletion_plan
compute_bootstrap_plan = _sd.compute_bootstrap_plan
_is_lexically_contained = _sd._is_lexically_contained


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


# ---------------------------------------------------------------------------
# compute_deletion_plan: old..new diff, the AC1 fixture-repo test list
# ---------------------------------------------------------------------------


async def test_a_deleted_file_is_planned_for_deletion(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    _write(repo / "comp" / "gone.py")
    commit_a = _commit_all(repo, "seed")
    (repo / "comp" / "gone.py").unlink()
    commit_b = _commit_all(repo, "delete gone.py")

    plan = await compute_deletion_plan(str(repo / "comp"), str(repo), commit_a, commit_b)

    assert plan.delete == ["gone.py"]
    assert plan.error is None


async def test_a_renamed_files_old_path_is_planned_for_deletion(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "old.py", "content")
    commit_a = _commit_all(repo, "seed")
    _git(repo, "mv", "comp/old.py", "comp/new.py")
    commit_b = _commit_all(repo, "rename")

    plan = await compute_deletion_plan(str(repo / "comp"), str(repo), commit_a, commit_b)

    assert plan.delete == ["old.py"]


async def test_a_never_tracked_file_is_not_in_the_diff_plan(tmp_path) -> None:
    """git diff itself never names a path it never tracked -- nothing to filter."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    commit_a = _commit_all(repo, "seed")
    commit_b = _commit_all(repo, "no-op")

    plan = await compute_deletion_plan(str(repo / "comp"), str(repo), commit_a, commit_b)

    assert plan.delete == []


async def test_same_commit_is_a_no_op(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    commit_a = _commit_all(repo, "seed")

    plan = await compute_deletion_plan(str(repo / "comp"), str(repo), commit_a, commit_a)

    assert plan.delete == [] and plan.kept == [] and plan.error is None


async def test_a_git_rm_cached_then_gitignored_file_is_kept(tmp_path) -> None:
    """#16300's pattern: git shows a `D`, but the file was deliberately kept."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "secrets.local.yaml", "token: abc\n")
    commit_a = _commit_all(repo, "seed")
    _git(repo, "rm", "--cached", "-q", "comp/secrets.local.yaml")
    _write(repo / "comp" / ".gitignore", "secrets.local.yaml\n")
    commit_b = _commit_all(repo, "untrack and ignore")

    plan = await compute_deletion_plan(str(repo / "comp"), str(repo), commit_a, commit_b)

    assert plan.delete == []
    assert "secrets.local.yaml" in plan.kept


async def test_a_host_state_excludes_match_is_kept(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "data" / "runtime.db")
    commit_a = _commit_all(repo, "seed")
    (repo / "comp" / "data" / "runtime.db").unlink()
    commit_b = _commit_all(repo, "delete data/runtime.db")

    plan = await compute_deletion_plan(str(repo / "comp"), str(repo), commit_a, commit_b)

    assert plan.delete == []
    assert "data/runtime.db" in plan.kept


async def test_a_diff_failure_reports_an_error_not_an_empty_plan(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    commit_a = _commit_all(repo, "seed")

    plan = await compute_deletion_plan(str(repo / "comp"), str(repo), commit_a, "0" * 40)

    assert plan.error is not None
    assert plan.delete == []


# ---------------------------------------------------------------------------
# _is_lexically_contained: MEDIUM 3, now lexical (the planner cannot resolve
# symlinks on a possibly-remote target)
# ---------------------------------------------------------------------------


def test_lexical_containment_rejects_traversal_and_absolute_paths() -> None:
    assert _is_lexically_contained("comp/keep.py") is True
    assert _is_lexically_contained("../outside.txt") is False
    assert _is_lexically_contained("comp/../../outside.txt") is False
    assert _is_lexically_contained("/etc/passwd") is False
    assert _is_lexically_contained("") is False


async def test_a_traversal_candidate_is_kept_not_deleted(tmp_path) -> None:
    """Belt-and-suspenders: even if git ever reported a traversal-shaped path,
    the plan must not propose deleting it."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    commit_a = _commit_all(repo, "seed")
    commit_b = _commit_all(repo, "no-op")

    plan = await compute_deletion_plan(str(repo / "comp"), str(repo), commit_a, commit_b)

    assert not any(".." in p or p.startswith("/") for p in plan.delete)


# ---------------------------------------------------------------------------
# compute_bootstrap_plan: no marker exists yet (owner decision B)
# ---------------------------------------------------------------------------


async def test_bootstrap_plans_a_tracked_then_deleted_file(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "gone.py")
    _commit_all(repo, "seed")
    (repo / "comp" / "gone.py").unlink()
    commit_b = _commit_all(repo, "delete gone.py")

    plan = await compute_bootstrap_plan(str(repo / "comp"), str(repo), commit_b, present_paths=["gone.py"])

    assert plan.delete == ["gone.py"]


async def test_bootstrap_keeps_a_never_tracked_file(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    commit_a = _commit_all(repo, "seed")

    plan = await compute_bootstrap_plan(
        str(repo / "comp"), str(repo), commit_a, present_paths=["keep.py", "host_state.env"]
    )

    assert plan.delete == []
    assert "host_state.env" not in plan.kept, "never-tracked is a different reason than kept-host-state"


async def test_bootstrap_keeps_a_gitignored_file(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "secrets.local.yaml", "token: abc\n")
    _commit_all(repo, "seed")
    _git(repo, "rm", "--cached", "-q", "comp/secrets.local.yaml")
    _write(repo / "comp" / ".gitignore", "secrets.local.yaml\n")
    commit_b = _commit_all(repo, "untrack and ignore")

    plan = await compute_bootstrap_plan(str(repo / "comp"), str(repo), commit_b, present_paths=["secrets.local.yaml"])

    assert plan.delete == []
    assert "secrets.local.yaml" in plan.kept


async def test_bootstrap_keeps_a_file_still_tracked_at_the_new_commit(tmp_path) -> None:
    """Present on the target, tracked once, and STILL tracked now -- not deleted
    from source at all, just not yet re-synced. Never a deletion candidate."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    commit_a = _commit_all(repo, "seed")

    plan = await compute_bootstrap_plan(str(repo / "comp"), str(repo), commit_a, present_paths=["keep.py"])

    assert plan.delete == []
