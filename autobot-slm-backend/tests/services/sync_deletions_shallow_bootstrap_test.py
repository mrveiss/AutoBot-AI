# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""compute_bootstrap_plan on a shallow clone (#16310).

Split out of tests/services/sync_deletions_test.py, which sits at its #14236
ceiling: a grandfathered file may not grow, so these tests -- entirely new,
not moved logic -- get their own file rather than pushing that one over.

update-all-nodes.yml's pre-flight checkout used ``depth: 1``, so the
bootstrap's own ``git log --diff-filter=AR`` saw only the one commit the
shallow fetch kept and reported "nothing to delete" -- an empty, error-free
plan that still got the marker written, permanently locking the target into
diff-mode from a baseline missing years of real deletions.

Same isolation contract as sync_deletions_test.py (see its module docstring
for the full rationale): lives under tests/services/, real-loads the same
service modules with the same sys.modules capture/restore, and exercises a
real, disposable git repository rather than a mock.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

_SERVICES_DIR = Path(__file__).parent.parent.parent / "services"


def _real_load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_SWAPPED = (
    "services",
    "services.git_tracker",
    "services.deploy_artifacts",
    "services.drift_checker",
    "services.deployed_dir_resolver",
    "services.git_subprocess",
    "services.host_state_filter",
    "services.sync_deletions",
)
_prev_modules = {name: sys.modules.get(name) for name in _SWAPPED}
try:
    _gt_stub = types.ModuleType("services.git_tracker")
    _gt_stub.DEFAULT_REPO_PATH = "/opt/autobot/code_source"  # type: ignore[attr-defined]
    sys.modules["services.git_tracker"] = _gt_stub

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

compute_bootstrap_plan = _sd.compute_bootstrap_plan

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
    _git(repo, "commit", "--allow-empty", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _shallow_clone(source: Path, dest: Path) -> None:
    """A REAL shallow clone (git itself decides what --depth 1 keeps), not a
    hand-rolled fixture pretending to be one -- the guard being tested calls
    git's own ``rev-parse --is-shallow-repository``, so the test fixture must
    produce whatever answer git itself gives on the real thing."""
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "--branch", "main", f"file://{source}", str(dest)],
        check=True,
        env=_GIT_ENV,
    )


async def test_bootstrap_refuses_to_run_on_a_shallow_clone(tmp_path) -> None:
    origin = tmp_path / "origin"
    _init_repo(origin)
    _write(origin / "comp" / "gone.py")
    _commit_all(origin, "seed")
    (origin / "comp" / "gone.py").unlink()
    commit_b = _commit_all(origin, "delete gone.py")

    clone = tmp_path / "clone"
    _shallow_clone(origin, clone)

    plan = await compute_bootstrap_plan(str(clone / "comp"), str(clone), commit_b, present_paths=["gone.py"])

    assert plan.delete == [], "a refused plan must not also claim something is safe to delete"
    assert plan.error, "a shallow clone must fail loudly, not silently plan an empty bootstrap"
    assert "shallow" in plan.error.lower()


async def test_bootstrap_runs_normally_on_the_same_history_once_unshallowed(tmp_path) -> None:
    """Control: the SAME clone, made full-depth, plans correctly -- proves the
    refusal above is really about shallowness, not something else about a
    cloned (vs. directly-committed-to) repository."""
    origin = tmp_path / "origin"
    _init_repo(origin)
    _write(origin / "comp" / "gone.py")
    _commit_all(origin, "seed")
    (origin / "comp" / "gone.py").unlink()
    commit_b = _commit_all(origin, "delete gone.py")

    clone = tmp_path / "clone"
    _shallow_clone(origin, clone)
    subprocess.run(["git", "-C", str(clone), "fetch", "--unshallow"], check=True, env=_GIT_ENV, capture_output=True)

    plan = await compute_bootstrap_plan(str(clone / "comp"), str(clone), commit_b, present_paths=["gone.py"])

    assert plan.error is None
    assert plan.delete == ["gone.py"]


async def test_a_non_shallow_repo_is_unaffected_by_the_guard(tmp_path) -> None:
    """Control: an ordinary (non-cloned) repo -- every other bootstrap test in
    sync_deletions_test.py -- must never be refused by this guard."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "gone.py")
    _commit_all(repo, "seed")
    (repo / "comp" / "gone.py").unlink()
    commit_b = _commit_all(repo, "delete gone.py")

    plan = await compute_bootstrap_plan(str(repo / "comp"), str(repo), commit_b, present_paths=["gone.py"])

    assert plan.error is None
    assert plan.delete == ["gone.py"]


def test_update_all_nodes_playbook_clones_code_source_at_full_depth() -> None:
    """The other half of the fix (#16310): even with the guard above, a
    permanently-shallow pre-flight checkout would refuse bootstrap on EVERY
    run forever, never actually cleaning up a target. The clone itself must
    not ask for `depth:`, matching pre-flight-code-sync.yml and
    provision-fleet-roles.yml, which already clone the same repo in full."""
    import yaml

    playbook_path = Path(__file__).resolve().parents[2] / "ansible" / "playbooks" / "update-all-nodes.yml"
    playbook = yaml.safe_load(playbook_path.read_text(encoding="utf-8"))

    tasks = [t for play in playbook for t in play.get("tasks", [])]
    clone_tasks = [t for t in tasks if isinstance(t.get("git"), dict) and t["git"].get("dest") == "{{ git_repo_root }}"]
    assert clone_tasks, "the code_source pre-flight clone task is no longer named/shaped as expected"
    for task in clone_tasks:
        assert "depth" not in task["git"], f"{task.get('name')}: shallow clone breaks sync_deletions bootstrap (#16310)"
