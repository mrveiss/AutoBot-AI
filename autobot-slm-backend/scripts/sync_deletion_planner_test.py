# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for scripts/sync_deletion_planner.py (#16310).

Real-loads the CLI module directly (bypassing ``services/__init__.py``,
which imports the full app stack -- DB, auth, deployment services --
unnecessary for this planner and unavailable in a bare test sandbox) rather
than invoking it as a subprocess, the same isolation
tests/services/sync_deletions_test.py uses for the library underneath it. Exercised
against a real, disposable git repository: the whole point of the CLI is to
answer questions only git can answer.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

_SCRIPTS_DIR = Path(__file__).parent
_SERVICES_DIR = _SCRIPTS_DIR.parent / "services"


def _real_load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# #16310 review round 7 (sys.modules leak guard): "services.git_tracker" is a
# SYNTHETIC stub (types.ModuleType, no __spec__), not a real load, and used to
# be installed here unconditionally with no restore -- it stayed in
# sys.modules for the rest of the session, visible to every test module that
# ran after this one. Folded into the same _SWAPPED/_prev_modules/finally
# cycle as the real-loaded modules below so it is captured and restored (or
# popped, if it was absent before) exactly like the rest.
#
# #16310 review round 9: "services" itself is ALSO captured/restored here --
# the guard's pre-push run named THIS file's
# test_diff_mode_prints_the_plan_as_json_and_exits_zero as where it first
# saw "services" go from conftest's synthetic MagicMock to a genuine module
# bound to this repo's own services/__init__.py
# ("exempt-refused: multi-source-root": "services" is a real,
# independently importable package under both autobot-backend/ and
# autobot-slm-backend/, so a genuine top-level binding reaching sys.modules
# here is ambiguous for any test that runs after this file and does an
# unqualified `import services`). Whatever in this bootstrap or the real
# CLI run reaches for it, restoring it in the same try/finally as every
# other name below removes the ambiguity rather than asking the guard to
# trust which "services" it is.
_SWAPPED = (
    "services",
    "services.git_tracker",
    "services.deploy_artifacts",
    "services.drift_checker",
    "services.deployed_dir_resolver",
    "services.git_subprocess",
    "services.host_state_filter",
    "services.sync_deletions",
    "sync_deletion_planner",
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
    _real_load("services.sync_deletions", _SERVICES_DIR / "sync_deletions.py")
    _planner = _real_load("sync_deletion_planner", _SCRIPTS_DIR / "sync_deletion_planner.py")
finally:
    for _name, _prev in _prev_modules.items():
        if _prev is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prev

main = _planner.main


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
    # #16310 review round 9: --allow-empty, matching tests/services/sync_deletions_test.py
    # and tests/services/full_tree_drift_test.py's identical helper -- a future
    # no-op-second-commit fixture here must not exit 1 either.
    _git(repo, "commit", "--allow-empty", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_diff_mode_prints_the_plan_as_json_and_exits_zero(tmp_path, capsys) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "gone.py")
    commit_a = _commit_all(repo, "seed")
    (repo / "comp" / "gone.py").unlink()
    commit_b = _commit_all(repo, "delete gone.py")

    exit_code = main(
        [
            "diff",
            "--repo-root",
            str(repo),
            "--source-dir",
            str(repo / "comp"),
            "--previous-commit",
            commit_a,
            "--new-commit",
            commit_b,
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"delete": ["gone.py"], "kept": [], "error": None}


def test_diff_mode_exits_nonzero_and_names_the_error_on_failure(tmp_path, capsys) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "keep.py")
    commit_a = _commit_all(repo, "seed")

    exit_code = main(
        [
            "diff",
            "--repo-root",
            str(repo),
            "--source-dir",
            str(repo / "comp"),
            "--previous-commit",
            commit_a,
            "--new-commit",
            "0" * 40,
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] is not None
    assert payload["delete"] == []


def test_bootstrap_mode_reads_present_paths_from_a_file(tmp_path, capsys) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "comp" / "gone.py")
    _commit_all(repo, "seed")
    (repo / "comp" / "gone.py").unlink()
    commit_b = _commit_all(repo, "delete gone.py")

    present_file = tmp_path / "present.txt"
    present_file.write_text("gone.py\n", encoding="utf-8")

    exit_code = main(
        [
            "bootstrap",
            "--repo-root",
            str(repo),
            "--source-dir",
            str(repo / "comp"),
            "--new-commit",
            commit_b,
            "--present-file",
            str(present_file),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["delete"] == ["gone.py"]
