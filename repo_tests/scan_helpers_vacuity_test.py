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

Every git call here runs under ``isolated_git_env()``. The pre-push hook runs
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
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import git, isolated_git_env, make_repo

_REPO_ROOT = repo_root()

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

#: Checkers on the shared ``run_check`` harness (#14896): a vacuous scan exits 2,
#: distinct from the 1 that means findings. The others still exit 1.
_HARNESS_CHECKERS = frozenset(
    {
        "check_no_kb_aioredis_access.py",
        "check_no_utcnow_isoformat.py",
        "check_no_live_install_sys_path_default.py",
        "check_no_hardcoded_ip_fallbacks.py",
        "check_no_llm_response_dict_access.py",
        "check_no_src_mock_path.py",
        "check_no_local_schemas.py",
    }
)

#: A file every checker in :data:`_BOTH_MODES` must rule clean, so the argv
#: assertion measures the floor and not some unrelated finding.
_CLEAN_SAMPLE = '''"""A module with nothing any of these hooks bans."""

VALUE = 1
'''


def _git(repo: Path, *args: str) -> None:
    """Run git in *repo* under the isolated env (#18940): no ambient hook GIT_DIR, no developer config."""
    git(repo, *args)


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
    make_repo(repo)
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
        # PYTHONPATH pinned to the REAL repo root (#17096 review): the copied
        # checker's own `from tools.lint...`/`from _scan_helpers import ...`
        # must resolve regardless of the calling shell's own PYTHONPATH --
        # empty in a bare `source .venv/bin/activate` shell, which made this
        # subprocess fail with `ModuleNotFoundError: No module named
        # 'tools.lint'` locally while a shell that happened to export it hid
        # the same gap.
        env={**isolated_git_env(), "PYTHONPATH": str(_REPO_ROOT)},
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
        env=isolated_git_env(),
    )
    tracked = [line for line in listing.stdout.splitlines() if line]

    assert tracked, "the fixture tracked nothing — the floor tests below would pass vacuously"
    assert (thin_repo / "sample.py").is_file()
    assert "sample.py" in tracked


@pytest.mark.parametrize("checker", _BOTH_MODES)
def test_a_full_repo_sweep_below_the_floor_refuses(thin_repo: Path, checker: str) -> None:
    """The defect #14896 names: a clean verdict from a sweep that reached nothing."""
    result = _run(thin_repo, checker)

    expected = 2 if checker in _HARNESS_CHECKERS else 1
    assert result.returncode == expected, f"{checker} passed a sweep it never made: {result.stdout}{result.stderr}"
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


@pytest.mark.parametrize(("unit", "expected"), [(None, "0 file(s); floor"), ("play(s)", "0 play(s); floor")])
def test_the_floor_refusal_names_what_was_counted(caplog: pytest.LogCaptureFixture, unit, expected: str) -> None:
    """A sweep that counts reads or plays must not report them as files (#18094 review)."""
    sys.path.insert(0, str(_REPO_ROOT / "tools" / "lint"))
    from _scan_helpers import enforce_reach  # noqa: PLC0415

    kwargs = {} if unit is None else {"unit": unit}
    with caplog.at_level("ERROR"):
        assert enforce_reach(0, 1, hook="probe", full_repo=True, **kwargs) == 1
    assert expected in caplog.text, caplog.text


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
    make_repo(repo)
    _seed(repo)
    for name in ("ssot_config.py", "ssot_tls.py"):
        shutil.copy2(_REPO_ROOT / "autobot_shared" / name, repo / "autobot_shared" / name)
    _git(repo, "add", "-A")

    result = _run(repo, "check_getenv_ssot_drift.py")

    assert result.returncode == 2, result.stdout + result.stderr
    assert _REFUSAL in result.stderr


def test_the_field_defaults_checker_refuses_a_sweep_that_matched_nothing(tmp_path: Path) -> None:
    """A different floor shape: the population is ``Field(...)`` calls in one
    file, not files in a tree. A stub ``ssot_config.py`` that parses but holds
    no fields is what a broken matcher produces, and it must not read clean."""
    repo = tmp_path / "field_repo"
    repo.mkdir()
    make_repo(repo)
    _seed(repo)
    (repo / "autobot_shared" / "ssot_config.py").write_text("CONFIG = {}\n", encoding="utf-8")
    _git(repo, "add", "-A")

    result = _run(repo, "check_field_defaults.py")

    assert result.returncode == 2, result.stdout + result.stderr
    assert _REFUSAL in result.stderr


def test_the_ansible_reference_checker_refuses_when_nothing_resolved(tmp_path: Path) -> None:
    """It printed its resolve count and returned 0 unconditionally until #14896,
    so a run that opened no play at all reported success with a zero in it."""
    repo = tmp_path / "ansible_repo"
    repo.mkdir()
    make_repo(repo)
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
        # See _run()'s own comment: pinned so this does not depend on the
        # calling shell's PYTHONPATH.
        env={**isolated_git_env(), "PYTHONPATH": str(_REPO_ROOT)},
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert _REFUSAL in result.stderr


# --- checkers on the shared run_check harness (#14896) -----------------------

#: ``(checker, source that violates it, finding text the output must carry, path to plant it at)``.
#: Banned literals are assembled from fragments so this file does not trip the
#: hooks it exercises.
_PLANTED = (
    ("check_no_kb_aioredis_access.py", "x = kb." + "_aioredis_client\n", "kb-private-aioredis-client", "planted.py"),
    (
        "check_no_utcnow_isoformat.py",
        "from datetime import datetime\nts = datetime." + "utcnow().isoformat()\n",
        "isoformat",
        "planted.py",
    ),
    (
        "check_no_live_install_sys_path_default.py",
        "import os, sys\nsys.path.insert(0, os.environ.get('X', '/opt/" + "autobot/code'))\n",
        "defaults to the live deployed install",
        "planted.py",
    ),
    (
        "check_no_hardcoded_ip_fallbacks.py",
        "import os\nh = os.getenv('H', '172.16." + "168.5')\n",
        "hardcoded fallback",
        "planted.py",
    ),
    (
        "check_no_llm_response_dict_access.py",
        "from m import LLMResponse\n\n\nasync def f(s):\n    r = await s.chat(1)\n    return r.get('content')\n",
        "LLMResponse is a Pydantic model",
        "planted.py",
    ),
    (
        "check_no_src_mock_path.py",
        "from unittest.mock import patch\n\npatch('sr" + "c.foo.bar')\n",
        "has no `src/` package",
        "planted_test.py",
    ),
    (
        "check_no_local_schemas.py",
        "from pydantic import BaseModel\n\n\nclass Foo(BaseModel):\n    x: int\n",
        "Local BaseModel subclass",
        "autobot-backend/api/planted.py",
    ),
)
_PLANTED_CHECKERS = [row[0] for row in _PLANTED]


def _run_isolated(repo: Path, checker: str, *args: str) -> subprocess.CompletedProcess:
    """Like :func:`_run`, but git may not climb out of *repo* into a parent checkout."""
    return subprocess.run(  # nosec B603  # fixed argv, no shell
        [sys.executable, str(repo / "tools" / "lint" / checker), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**isolated_git_env(), "PYTHONPATH": str(_REPO_ROOT), "GIT_CEILING_DIRECTORIES": str(repo.parent)},
    )


@pytest.mark.parametrize(
    ("checker", "source", "finding", "rel"),
    _PLANTED,
    # Named by checker, never by source: a planted literal (e.g. a fleet address split in the
    # source above) would otherwise be rejoined into the node id and land in .test_durations.
    ids=[f"{row[0]}-{row[3]}" for row in _PLANTED],
)
def test_a_planted_violation_still_exits_one(
    thin_repo: Path, checker: str, source: str, finding: str, rel: str
) -> None:
    planted = thin_repo / rel
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text(source, encoding="utf-8")
    try:
        result = _run(thin_repo, checker, rel)
    finally:
        planted.unlink()

    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{rel}:" in result.stderr and finding in result.stderr


@pytest.mark.parametrize("checker", _PLANTED_CHECKERS)
def test_a_non_git_root_exits_two(tmp_path: Path, checker: str) -> None:
    """Copied beside no repository, the checker has no root to scan: not a clean pass."""
    _seed(tmp_path)

    result = _run_isolated(tmp_path, checker, "sample.py")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "cannot anchor the scan" in result.stderr


@pytest.mark.parametrize("checker", _PLANTED_CHECKERS)
def test_a_full_repo_sweep_that_enumerates_nothing_exits_two(tmp_path: Path, checker: str) -> None:
    """A repository tracking no Python at all: nothing was scanned, so nothing may read clean."""
    make_repo(tmp_path)
    _seed(tmp_path)
    (tmp_path / "notes.txt").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "notes.txt")  # the checkers themselves stay untracked

    result = _run_isolated(tmp_path, checker)

    assert result.returncode == 2, result.stdout + result.stderr


@pytest.mark.parametrize("checker", _PLANTED_CHECKERS)
def test_the_checker_answers_the_same_from_a_subdirectory(thin_repo: Path, checker: str) -> None:
    """The root comes from the checker's own file (``resolve_root``), never the launch directory.

    A full-repo run below the floor prints how many files it reached, so equal
    stderr from the repo root and from ``tools/`` means equal reach. A root
    taken from the cwd would name ``tools/`` here, which is not a toplevel, and
    the two runs would differ.
    """
    script = thin_repo / "tools" / "lint" / checker
    runs = [
        subprocess.run(  # nosec B603  # fixed argv, no shell
            [sys.executable, str(script)],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**isolated_git_env(), "PYTHONPATH": str(_REPO_ROOT)},
        )
        for cwd in (thin_repo, thin_repo / "tools")
    ]

    assert runs[0].returncode == runs[1].returncode == 2
    assert "reached only" in runs[0].stderr
    assert (runs[0].stdout, runs[0].stderr) == (runs[1].stdout, runs[1].stderr)


def test_an_untracked_script_on_disk_is_not_mistaken_for_a_failed_enumeration(tmp_path: Path) -> None:
    """A doc names ``scripts/x.sh``; the file exists but git does not track it.

    That is "not executable" (a finding, exit 1), not a broken enumeration
    (exit 2). Run as a subprocess so it goes through the real import paths:
    this script imports ``tools.lint._scan_helpers`` while the harness imports
    ``_scan_helpers`` bare, and two module copies mean two ``EmptyEnumeration``
    classes -- an ``except`` against one never matches the other.
    """
    make_repo(tmp_path)
    _seed(tmp_path)
    shutil.copy2(_REPO_ROOT / "tools" / "__init__.py", tmp_path / "tools" / "__init__.py")
    (tmp_path / "scripts").mkdir()
    shutil.copy2(
        _REPO_ROOT / "scripts" / "check_script_exec_bits.py", tmp_path / "scripts" / "check_script_exec_bits.py"
    )
    (tmp_path / "scripts" / "x.sh").write_text("#!/bin/sh\n", encoding="utf-8")  # on disk, never staged
    (tmp_path / "README.md").write_text("run scripts/x.sh -v\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")

    result = subprocess.run(  # nosec B603  # fixed argv, no shell
        [sys.executable, str(tmp_path / "scripts" / "check_script_exec_bits.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**isolated_git_env(), "GIT_CEILING_DIRECTORIES": str(tmp_path.parent)},
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "runs scripts/x.sh directly" in result.stdout


def _load_by_path(path: Path, name: str):
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nosec_format_does_not_pass_when_git_cannot_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """It ignored git's return code, so a non-checkout read as zero files and exit 0."""
    module = _load_by_path(_REPO_ROOT / "scripts" / "check_nosec_format.py", "_nosec_probe_nongit")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    assert module.main() == 2


def test_nosec_format_does_not_pass_when_git_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_by_path(_REPO_ROOT / "scripts" / "check_nosec_format.py", "_nosec_probe_rc")

    class _Failed:
        returncode = 128
        stdout = ""
        stderr = "fatal: not a git repository"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Failed())

    assert module.main() == 2


def test_script_exec_bits_does_not_pass_when_git_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_by_path(_REPO_ROOT / "scripts" / "check_script_exec_bits.py", "_exec_bits_probe_rc")

    class _Failed:
        returncode = 128
        stdout = ""
        stderr = "fatal: not a git repository"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Failed())

    assert module.main() == 2
