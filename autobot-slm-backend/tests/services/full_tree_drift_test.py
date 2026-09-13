# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services/full_tree_drift.py (#16310).

Owner requirement, 11 Sep 2026: every file under a deployed component gets one
of four verdicts -- modified, removed_from_source (drift), build_bundle or
host_state (named exclusions) -- and a run over an empty or unreadable tree
fails loudly rather than reporting no drift. Exercised against a real,
disposable git repository, the same way tests/services/sync_deletions_test.py
is: the removed_from_source verdict is specifically a claim about what
``git log`` says, which a mock cannot stand in for.

Bootstrap mirrors tests/services/sync_deletions_test.py.

#16310 review round 10: lives under tests/services/, not co-located with
full_tree_drift.py in services/, on purpose. autobot-slm-backend/services/
has its own __init__.py, so pytest's own collection of a test module living
there imports the real "services" package (needed to bind
services.full_tree_drift_test as an attribute) BEFORE this file's top-level
code runs -- by the time the _SWAPPED/_prev_modules capture below executes,
"services" is already the genuine package, and restoring "whatever it was"
just puts the genuine package straight back. Neither round 7's nor round
9's capture/restore could have fixed that; both ran too late.
tests/services/conftest.py (#11478/#13084) already solves exactly this for
this whole directory: it replaces sys.modules["services"] with a hollow,
real-path ModuleType (spec-less, so still "synthetic" to the leak guard)
BEFORE pytest collects anything here, so pytest's own package-parent
resolution finds that hollow package already in place and never touches
services/__init__.py at all. Moved here rather than adding a sibling
services/conftest.py: that would apply to every OTHER co-located
services/*_test.py file too (~30 of them, none audited for reliance on
services.<name> auto-fabricating a MagicMock), where this move only affects
the two files that actually need the fix.
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


# #16310 review round 7 (sys.modules leak guard): "services.git_tracker" is
# a SYNTHETIC stub (types.ModuleType, no __spec__) and used to be installed
# unconditionally with no restore, same bug as
# tests/services/sync_deletions_test.py and
# scripts/sync_deletion_planner_test.py. Folded into this file's own
# _SWAPPED/_prev_modules/finally cycle so it is captured and restored (or
# popped, if it was absent) like every other name here.
#
# "services" is ALSO listed, defensively, though this module living under
# tests/services/ (round 10, see the module docstring) means
# tests/services/conftest.py has already replaced it with a hollow
# real-path package before this file's top-level code runs -- the
# _prev_modules capture below sees that hollow package, not a genuine one,
# and the restore is a same-value no-op either way.
_SWAPPED = (
    "services",
    "services.git_tracker",
    "services.deploy_artifacts",
    "services.drift_checker",
    "services.deployed_dir_resolver",
    "services.git_subprocess",
    "services.host_state_filter",
    "services.full_tree_drift",
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
finally:
    for _name, _prev in _prev_modules.items():
        if _prev is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prev

compute_full_tree_drift = _ftd.compute_full_tree_drift
VERDICT_MODIFIED = _ftd.VERDICT_MODIFIED
VERDICT_REMOVED_FROM_SOURCE = _ftd.VERDICT_REMOVED_FROM_SOURCE


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


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    # #16310 review round 9: --allow-empty, matching tests/services/sync_deletions_test.py
    # and scripts/sync_deletion_planner_test.py's identical helper -- a
    # future no-op-second-commit fixture here must not exit 1 either.
    _git(repo, "commit", "--allow-empty", "-q", "-m", message)


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


async def _drift_for(tmp_path, monkeypatch, component: str, repo: Path):
    monkeypatch.setattr(_ftd, "get_live_dir", lambda c: str(tmp_path / "deployed" / c))
    monkeypatch.setattr(_ftd, "get_default_source_dir", lambda c: str(repo / c))
    return await compute_full_tree_drift(component, repo_root=str(repo))


def _by_path(result, path: str):
    return next((entry for entry in result.drifted if entry.path == path), None)


async def test_modified_file_gets_modified_verdict(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "config.yaml", "a: 1\n")
    _commit_all(repo, "seed")

    _write(tmp_path / "deployed" / "comp" / "config.yaml", "a: 2\n")

    result = await _drift_for(tmp_path, monkeypatch, "comp", repo)

    entry = _by_path(result, "config.yaml")
    assert entry is not None and entry.verdict == VERDICT_MODIFIED


async def test_removed_from_source_file_gets_its_verdict_and_commit(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    _write(repo / "comp" / "gone.py")
    _commit_all(repo, "seed")
    (repo / "comp" / "gone.py").unlink()
    _commit_all(repo, "delete gone.py")

    _write(tmp_path / "deployed" / "comp" / "keep.py")
    _write(tmp_path / "deployed" / "comp" / "gone.py")

    result = await _drift_for(tmp_path, monkeypatch, "comp", repo)

    entry = _by_path(result, "gone.py")
    assert entry is not None
    assert entry.verdict == VERDICT_REMOVED_FROM_SOURCE
    assert entry.detail  # the commit that removed it is named, not just flagged
    assert _by_path(result, "keep.py") is None, "a file present on both sides must not be reported"


async def test_never_tracked_file_gets_a_named_host_state_exclusion(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    _commit_all(repo, "seed")

    _write(tmp_path / "deployed" / "comp" / "keep.py")
    _write(tmp_path / "deployed" / "comp" / "data" / "runtime.db")  # never tracked in the fixture repo

    result = await _drift_for(tmp_path, monkeypatch, "comp", repo)

    assert _by_path(result, "data/runtime.db") is None, "host state is excluded, never reported as drift"
    assert result.exclusions.get("host_state:data") == 1


async def test_build_bundle_is_excluded_and_named(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    _commit_all(repo, "seed")

    _write(tmp_path / "deployed" / "comp" / "keep.py")
    _write(tmp_path / "deployed" / "comp" / "dist-20260101T000000000Z" / "index.html")

    result = await _drift_for(tmp_path, monkeypatch, "comp", repo)

    assert not any(entry.path.startswith("dist-") for entry in result.drifted)
    assert result.exclusions.get("build_bundle") == 1


async def test_an_empty_deployed_tree_fails_loudly(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    _commit_all(repo, "seed")

    (tmp_path / "deployed" / "comp").mkdir(parents=True)  # exists, colocated, but empty

    result = await _drift_for(tmp_path, monkeypatch, "comp", repo)

    assert result.error is not None
    assert result.drifted == [] and result.compared == 0, "an empty tree must never read as clean"


async def test_a_component_not_colocated_here_is_skipped_not_errored(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    _commit_all(repo, "seed")
    # deployed/comp is never created -- not colocated on this host.

    result = await _drift_for(tmp_path, monkeypatch, "comp", repo)

    assert result.skipped is True
    assert result.error is None


async def test_a_git_rm_cached_then_gitignored_file_reads_as_host_state(tmp_path, monkeypatch) -> None:
    """#16310 review (MEDIUM 4): a file that was `git rm --cached` then
    gitignored still has git history -- checking history before the
    host-state/ignored check would label it removed_from_source and steer an
    operator into deleting a live key by hand (#16300's pattern).

    #16310 review round 7, real bug: `git rm --cached` never touches the
    working tree, so this file stays physically present in the CONTROLLER's
    own source checkout with unchanged content -- byte-identical to the
    deployed copy below. `_walk_checksums` (a raw filesystem walk of
    source_dir, not a git query) saw that match and
    `_classify_all_paths` read it as "no drift", `continue`-ing before ever
    reaching `_classify_deployed_only` -- the git-history-aware check this
    docstring's first paragraph is about. Fixed by `_source_ignored_paths`
    excluding source-side paths git ignores before the checksum comparison
    runs at all. Same fixture, same real host layout, as
    tests/services/sync_deletions_test.py::test_a_git_rm_cached_then_gitignored_file_is_kept
    -- that one was never affected (compute_deletion_plan is entirely
    git-diff/git-log driven and never walks source_dir's raw disk), which is
    the proof this is a full_tree_drift.py-specific bug, not a shared one.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "secrets.local.yaml", "token: abc\n")
    _commit_all(repo, "seed")
    _git(repo, "rm", "--cached", "-q", "comp/secrets.local.yaml")
    _write(repo / "comp" / ".gitignore", "secrets.local.yaml\n")
    _commit_all(repo, "untrack and ignore secrets.local.yaml")

    _write(tmp_path / "deployed" / "comp" / "secrets.local.yaml", "token: abc\n")

    result = await _drift_for(tmp_path, monkeypatch, "comp", repo)

    entry = _by_path(result, "secrets.local.yaml")
    assert entry is None, "a kept, gitignored file must never be reported as removed_from_source"
    assert result.exclusions.get("host_state:gitignored") == 1
