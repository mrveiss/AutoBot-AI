# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A full-repo sweep that lost its reach must fail; a pre-commit run must not (#14896).

Both halves are load-bearing, and the second one is the reason this file is not
optional:

* **Full-repo mode** is where "found nothing" is indistinguishable from "the
  sweep broke". Every checker below is run against a throwaway repository
  holding a handful of files, which is exactly what a lost sweep looks like,
  and each must exit 1 saying ``FIX THE SWEEP``.
* **Explicit-argv mode** is pre-commit. It hands a hook the changed files and
  nothing else, so a PR touching one file legitimately gives a hook one file --
  or zero. A floor applied there reddens every pull request in the repository.
  The ``exit 0`` assertions are what stop that, so they are asserted for the
  same checkers, in the same test, over the same fixture.

WHY A THROWAWAY REPOSITORY AND NOT A MONKEYPATCH
------------------------------------------------
The floor's whole subject is ``git ls-files`` returning less than it should.
Stubbing the enumeration would assert that the comparison operator works while
leaving the thing being compared -- a real git enumeration, anchored at a real
root, run with a real environment -- untested. The checkers resolve their root
from ``__file__``, so the tree is copied to the same relative depth and the
copies answer with the throwaway root.

Every git call here passes ``env=scrubbed_git_env()``. The pre-push hook runs
this suite with ``GIT_DIR`` pointing at the worktree being pushed, and an
unscrubbed ``git init``/``git add`` in a fixture then operates on THAT
repository rather than ``tmp_path`` -- measured, twice, in #15490.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
import sys
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: The refusal every converted checker must print. Asserted as a literal so a
#: reworded message cannot quietly stop being findable by the people it is for.
_REFUSAL = "FIX THE SWEEP"

#: Checkers whose full-repo floor is a count of swept ``*.py`` files, and which
#: also accept an explicit file list from pre-commit. Both modes are asserted.
_BOTH_MODES = (
    "check_decorator_order.py",
    "check_no_blocking_io_in_async.py",
    "check_no_hardcoded_ip_fallbacks.py",
    "check_no_kb_aioredis_access.py",
    "check_no_live_install_sys_path_default.py",
    "check_no_llm_response_dict_access.py",
    "check_no_local_schemas.py",
    "check_no_src_mock_path.py",
    "check_no_utcnow_isoformat.py",
    "check_response_models.py",
    # Migrated onto the shared helper in #14896, keeping their own numbers:
    # 1 file per language, and 1500 test files respectively.
    "check_git_toplevel_env_scrubbed.py",
    "check_git_write_env_scrubbed.py",
)

#: A file every checker in :data:`_BOTH_MODES` must rule clean, so the argv
#: assertion measures the floor and not some unrelated finding.
_CLEAN_SAMPLE = '''"""A module with nothing any of these hooks bans."""

VALUE = 1
'''


def _git(repo: Path, *args: str) -> None:
    """Run git in *repo* with the ambient hook environment scrubbed."""
    subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
    )


def _seed(repo: Path) -> None:
    """Copy the checkers and their one dependency to the same relative depth."""
    lint = repo / "tools" / "lint"
    lint.mkdir(parents=True)
    for source in sorted((_REPO_ROOT / "tools" / "lint").glob("*.py")):
        if not source.name.endswith("_test.py"):
            shutil.copy2(source, lint / source.name)
    shared = repo / "autobot_shared"
    shared.mkdir()
    # paths.py is deliberately stdlib-only, so the copy needs nothing else.
    shutil.copy2(_REPO_ROOT / "autobot_shared" / "paths.py", shared / "paths.py")
    (repo / "sample.py").write_text(_CLEAN_SAMPLE, encoding="utf-8")


@pytest.fixture(scope="module")
def thin_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A tracked repository far below every floor in the repository."""
    repo = tmp_path_factory.mktemp("thin_repo")
    _git(repo, "init", "-q")
    _seed(repo)
    _git(repo, "add", "-A")
    return repo


def _run(repo: Path, checker: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603  # fixed argv, no shell
        [sys.executable, str(repo / "tools" / "lint" / checker), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=scrubbed_git_env(),
    )


def test_the_throwaway_repo_is_actually_a_repo(thin_repo: Path) -> None:
    """Guards every assertion below: a fixture that failed to initialise would
    make each checker fail for the wrong reason and still look green."""
    listing = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=thin_repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        env=scrubbed_git_env(),
    )
    tracked = [line for line in listing.stdout.splitlines() if line]

    assert tracked, "the fixture tracked nothing — the floor tests below would pass vacuously"
    assert (thin_repo / "sample.py").is_file()
    assert "sample.py" in tracked


@pytest.mark.parametrize("checker", _BOTH_MODES)
def test_a_full_repo_sweep_below_the_floor_refuses(thin_repo: Path, checker: str) -> None:
    """The defect #14896 names: a clean verdict from a sweep that reached nothing."""
    result = _run(thin_repo, checker)

    assert result.returncode == 1, f"{checker} passed a sweep it never made: {result.stdout}{result.stderr}"
    assert _REFUSAL in result.stderr, f"{checker} failed without saying why:\n{result.stderr}"


@pytest.mark.parametrize("checker", _BOTH_MODES)
def test_an_explicit_single_file_argv_is_not_floored(thin_repo: Path, checker: str) -> None:
    """This is the assertion that protects every other PR in the repository.

    pre-commit passes changed files. A hook that applied its full-repo floor to
    that argv would fail on every small PR — the floor would have turned a
    vacuity guard into a repository-wide outage.
    """
    result = _run(thin_repo, checker, "sample.py")

    assert result.returncode == 0, f"{checker} floored an explicit argv:\n{result.stderr}"
    assert _REFUSAL not in result.stderr


def test_tracked_paths_raises_rather_than_returning_empty(thin_repo: Path) -> None:
    """``[]`` and "the enumeration broke" must not be the same value.

    Returning empty is how a failed enumeration reads as a clean tree three
    frames later, where the return code is gone and only the list is left.
    """
    sys.path.insert(0, str(_REPO_ROOT / "tools" / "lint"))
    from _scan_helpers import tracked_paths  # noqa: PLC0415

    assert tracked_paths(thin_repo, "*.py"), "the fixture should enumerate"

    with pytest.raises(RuntimeError, match="listed nothing"):
        tracked_paths(thin_repo, "*.no-such-suffix")

    with pytest.raises(RuntimeError, match="failed"):
        tracked_paths(thin_repo / "tools", "--not-a-flag")


def test_enforce_reach_is_silent_outside_full_repo_mode() -> None:
    """The rule in isolation, so a caller reading the helper cannot mistake it.

    ``full_repo=False`` returns 0 for *any* count, zero included: that is the
    pre-commit path, and pre-commit legitimately passes no matching files.
    """
    sys.path.insert(0, str(_REPO_ROOT / "tools" / "lint"))
    from _scan_helpers import PY_FLOOR, enforce_reach  # noqa: PLC0415

    assert enforce_reach(0, PY_FLOOR, hook="probe", full_repo=False) == 0
    assert enforce_reach(0, PY_FLOOR, hook="probe", full_repo=True) == 1
    assert enforce_reach(PY_FLOOR, PY_FLOOR, hook="probe", full_repo=True) == 0


def test_the_py_floor_leaves_headroom_over_the_real_tree() -> None:
    """A floor set at the current count fails on the first subtree that moves;
    one set near zero catches nothing. Both directions are pinned."""
    sys.path.insert(0, str(_REPO_ROOT / "tools" / "lint"))
    from _scan_helpers import PY_FLOOR, tracked_paths  # noqa: PLC0415

    tracked = tracked_paths(_REPO_ROOT, "*.py")

    assert len(tracked) >= PY_FLOOR, f"the real tree has {len(tracked)} tracked .py files, under the floor"
    assert PY_FLOOR >= len(tracked) * 0.5, "the floor has drifted so far below the tree that it asserts little"


def test_the_getenv_drift_checker_refuses_a_lost_sweep(thin_repo: Path, tmp_path: Path) -> None:
    """Full-repo only by construction: a call-site default and the ssot_config
    field it contradicts live in different files, so there is no argv mode to
    assert. Needs a real ``ssot_config.py`` — its own field-default floor is
    checked before the file sweep is."""
    repo = tmp_path / "drift_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _seed(repo)
    shutil.copy2(_REPO_ROOT / "autobot_shared" / "ssot_config.py", repo / "autobot_shared" / "ssot_config.py")
    _git(repo, "add", "-A")

    result = _run(repo, "check_getenv_ssot_drift.py")

    assert result.returncode == 1, result.stdout + result.stderr
    assert _REFUSAL in result.stderr


def test_the_field_defaults_checker_refuses_a_sweep_that_matched_nothing(tmp_path: Path) -> None:
    """A different floor shape: the population is ``Field(...)`` calls in one
    file, not files in a tree. A stub ``ssot_config.py`` that parses but holds
    no fields is what a broken matcher produces, and it must not read clean."""
    repo = tmp_path / "field_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _seed(repo)
    (repo / "autobot_shared" / "ssot_config.py").write_text("CONFIG = {}\n", encoding="utf-8")
    _git(repo, "add", "-A")

    result = _run(repo, "check_field_defaults.py")

    assert result.returncode == 1, result.stdout + result.stderr
    assert _REFUSAL in result.stderr


def test_the_ansible_reference_checker_refuses_when_nothing_resolved(tmp_path: Path) -> None:
    """It printed its resolve count and returned 0 unconditionally until #14896,
    so a run that opened no play at all reported success with a zero in it."""
    repo = tmp_path / "ansible_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _seed(repo)
    scripts = repo / "scripts"
    scripts.mkdir()
    shutil.copy2(
        _REPO_ROOT / "scripts" / "check_ansible_file_references.py",
        scripts / "check_ansible_file_references.py",
    )
    _git(repo, "add", "-A")

    result = subprocess.run(  # nosec B603  # fixed argv, no shell
        [sys.executable, str(scripts / "check_ansible_file_references.py")],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=scrubbed_git_env(),
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert _REFUSAL in result.stderr
