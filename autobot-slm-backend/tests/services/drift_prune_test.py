# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for services/drift_prune.py (#22082): contrast pairs on a real git repository.

A ``removed_from_source`` file is removed; ``host_state``, artifact and ``modified``
files are untouched even when a caller asks for them by name; the ``plugins``
component is accepted. Bootstrapped like tests/services/full_tree_drift_test.py
(see its docstring for why this lives under tests/services/).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

from autobot_shared.isolated_git import git, make_repo

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
    "services.full_tree_drift",
    "services.drift_prune",
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
    _ftd = _real_load("services.full_tree_drift", _SERVICES_DIR / "full_tree_drift.py")
    _dp = _real_load("services.drift_prune", _SERVICES_DIR / "drift_prune.py")
finally:
    for _name, _prev in _prev_modules.items():
        if _prev is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prev

plan_prune = _dp.plan_prune
apply_prune = _dp.apply_prune
is_prunable_component = _dp.is_prunable_component


def _git(repo: Path, *args: str) -> str:
    return git(repo, *args).stdout.strip()


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "--allow-empty", "-q", "-m", message)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup(tmp_path, monkeypatch, component: str, source_rel: str | None = None):
    """A repo whose *component* source once had gone.py (deleted) and keep.py (kept)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    make_repo(repo, default_branch="main")
    src = repo / (source_rel or component)
    _write(src / "keep.py", "k = 1\n")
    _write(src / "gone.py")
    _write(src / "other_gone.py")
    _commit_all(repo, "seed")
    (src / "gone.py").unlink()
    (src / "other_gone.py").unlink()
    _commit_all(repo, "delete two files")
    deployed = tmp_path / "deployed" / component
    for name in ("keep.py", "gone.py", "other_gone.py"):
        _write(deployed / name, "k = 1\n" if name == "keep.py" else "x")
    monkeypatch.setattr(_ftd, "get_live_dir", lambda c: str(deployed))
    monkeypatch.setattr(_ftd, "get_default_source_dir", lambda c: str(src))
    return repo, deployed


def _paths(plan) -> list[str]:
    return sorted(path for path, _ in plan.files)


async def test_plan_lists_only_removed_from_source_files(tmp_path, monkeypatch) -> None:
    repo, deployed = _setup(tmp_path, monkeypatch, "autobot-browser-worker")
    _write(deployed / "package-lock.json")  # never tracked: host state, generated on the host
    _write(deployed / "keep.py", "k = 2\n")  # modified
    _write(deployed / "node_modules" / "pkg" / "index.js")  # artifact

    plan = await plan_prune("autobot-browser-worker", str(repo))

    assert plan.error is None
    assert _paths(plan) == ["gone.py", "other_gone.py"], plan.files
    assert all(commit for _, commit in plan.files), "each entry names the commit that removed it"


async def test_confirmed_removed_from_source_files_are_removed_and_nothing_else(tmp_path, monkeypatch) -> None:
    repo, deployed = _setup(tmp_path, monkeypatch, "autobot-browser-worker")
    _write(deployed / "package-lock.json", "{}")
    _write(deployed / "keep.py", "k = 2\n")  # modified
    _write(deployed / "node_modules" / "pkg" / "index.js")

    result = await apply_prune("autobot-browser-worker", ["gone.py", "other_gone.py"], str(repo))

    assert sorted(result.removed) == ["gone.py", "other_gone.py"]
    assert not (deployed / "gone.py").exists() and not (deployed / "other_gone.py").exists()
    assert _read(deployed / "package-lock.json") == "{}"
    assert _read(deployed / "keep.py") == "k = 2\n"
    assert (deployed / "node_modules" / "pkg" / "index.js").exists()


async def test_a_crafted_list_naming_host_state_artifact_and_modified_files_removes_none_of_them(
    tmp_path, monkeypatch
) -> None:
    repo, deployed = _setup(tmp_path, monkeypatch, "autobot-browser-worker")
    _write(deployed / "package-lock.json")
    _write(deployed / "keep.py", "k = 2\n")
    _write(deployed / "data" / "runtime.db")
    _write(deployed / "node_modules" / "pkg" / "index.js")
    asked = ["package-lock.json", "keep.py", "data/runtime.db", "node_modules/pkg/index.js", "gone.py"]

    result = await apply_prune("autobot-browser-worker", asked, str(repo))

    assert result.removed == ["gone.py"]
    assert sorted(result.refused) == sorted(asked[:-1]), result.refused
    for survivor in asked[:-1]:
        assert (deployed / survivor).exists(), f"{survivor} must be untouched"


async def test_only_the_confirmed_subset_is_removed(tmp_path, monkeypatch) -> None:
    repo, deployed = _setup(tmp_path, monkeypatch, "autobot-browser-worker")

    result = await apply_prune("autobot-browser-worker", ["gone.py"], str(repo))

    assert result.removed == ["gone.py"]
    assert (deployed / "other_gone.py").exists(), "an eligible file the operator did not confirm stays"


async def test_a_path_that_stopped_being_eligible_since_the_preview_is_refused(tmp_path, monkeypatch) -> None:
    repo, deployed = _setup(tmp_path, monkeypatch, "autobot-browser-worker")
    plan = await plan_prune("autobot-browser-worker", str(repo))
    assert "gone.py" in _paths(plan)
    _write(repo / "autobot-browser-worker" / "gone.py")  # source has it again: now plain drift, not debris
    _commit_all(repo, "restore gone.py")

    result = await apply_prune("autobot-browser-worker", _paths(plan), str(repo))

    assert "gone.py" in result.refused and (deployed / "gone.py").exists()
    assert result.removed == ["other_gone.py"]


async def test_the_plugins_component_is_accepted_and_pruned(tmp_path, monkeypatch) -> None:
    assert is_prunable_component("plugins") is True
    assert is_prunable_component("not-a-component") is False
    repo, deployed = _setup(tmp_path, monkeypatch, "plugins", source_rel="plugins/core-plugins/telemetry")

    plan = await plan_prune("plugins", str(repo))
    result = await apply_prune("plugins", _paths(plan), str(repo))

    assert _paths(plan) == ["gone.py", "other_gone.py"]
    assert sorted(result.removed) == ["gone.py", "other_gone.py"]
    assert (deployed / "keep.py").exists()


async def test_a_traversal_or_symlinked_parent_never_leaves_the_deployed_tree(tmp_path, monkeypatch) -> None:
    repo, deployed = _setup(tmp_path, monkeypatch, "autobot-browser-worker")
    outside = tmp_path / "outside"
    _write(outside / "gone.py", "precious")
    os.symlink(outside, deployed / "link")

    for escape in ("../outside/gone.py", "link/gone.py", "/etc/hostname"):
        _, reason = _dp._unlink_one(str(deployed), escape)
        assert reason, escape
    assert _read(outside / "gone.py") == "precious"


async def test_a_component_that_cannot_be_judged_removes_nothing(tmp_path, monkeypatch) -> None:
    repo, deployed = _setup(tmp_path, monkeypatch, "autobot-browser-worker")
    monkeypatch.setattr(_ftd, "get_live_dir", lambda c: str(tmp_path / "nowhere"))  # not colocated: skipped

    result = await apply_prune("autobot-browser-worker", ["gone.py"], str(repo))

    assert result.removed == [] and "gone.py" in result.refused
    assert (deployed / "gone.py").exists()


async def test_a_leaf_symlink_is_removed_and_its_target_stays(tmp_path, monkeypatch) -> None:
    repo, deployed = _setup(tmp_path, monkeypatch, "autobot-browser-worker")
    src = repo / "autobot-browser-worker"
    _write(src / "linked.py")
    _commit_all(repo, "add linked.py")
    (src / "linked.py").unlink()
    _commit_all(repo, "delete linked.py")
    target = tmp_path / "elsewhere.txt"
    _write(target, "keep me")
    os.symlink(target, deployed / "linked.py")

    result = await apply_prune("autobot-browser-worker", ["linked.py"], str(repo))

    assert result.removed == ["linked.py"], (result.refused, result.failed)
    assert not os.path.lexists(deployed / "linked.py")
    assert _read(target) == "keep me", "unlinking the link must never touch what it points at"


async def test_a_directory_path_is_refused(tmp_path, monkeypatch) -> None:
    repo, deployed = _setup(tmp_path, monkeypatch, "autobot-browser-worker")
    _write(deployed / "sub" / "inner.txt")

    removed, reason = _dp._unlink_one(str(deployed), "sub")
    result = await apply_prune("autobot-browser-worker", ["sub"], str(repo))

    assert (removed, reason) == (False, "is a directory")
    assert result.removed == [] and "sub" in result.refused
    assert (deployed / "sub" / "inner.txt").exists()


async def test_a_failing_last_moment_check_removes_nothing(tmp_path, monkeypatch) -> None:
    repo, deployed = _setup(tmp_path, monkeypatch, "autobot-browser-worker")

    async def _deploy_started() -> None:
        raise RuntimeError("a deploy started")

    try:
        await apply_prune("autobot-browser-worker", ["gone.py"], str(repo), before_delete=_deploy_started)
    except RuntimeError:
        pass
    else:
        raise AssertionError("the check's failure must propagate")
    assert (deployed / "gone.py").exists()
