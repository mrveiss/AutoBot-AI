# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The two single-target checkers on the shared harness: exit 2 on a vacuous scan (#14896).

``check_field_defaults``, ``check_getenv_ssot_drift`` and ``check_env_forks`` always sweep the whole
tree -- there is no argv mode, so they cannot join the per-file parametrised set
in ``scan_helpers_vacuity_test``. Their three properties are asserted here against
copies of the checker run in a throwaway repository, the same way:

* **AC1** the launch directory changes nothing: identical rc, stdout and stderr
  from the repository root and from ``tools/``.
* **AC2** a root that is not a git toplevel, a repository without ``ssot_config``
  and a population below its floor each exit 2, never 0 and never 1.
* **AC3** a planted violation still exits 1 -- and the identical repository
  without it exits 0, so the 1 is the violation and not the fixture.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from repo_tests.scan_helpers_vacuity_test import _REPO_ROOT, _git, _run_isolated, _seed

from autobot_shared.isolated_git import isolated_git_env, make_repo
from tools.lint import check_getenv_ssot_drift  # noqa: F401 -- puts tools/lint on sys.path for the sibling import
from tools.lint._scan_helpers import PY_FLOOR

from tools.lint._env_fork_scan import FORK_READ_FLOOR, KNOWN_ENV_FORKS  # isort: skip

_CHECKERS = ("check_field_defaults.py", "check_getenv_ssot_drift.py", "check_env_forks.py")
#: Assembled from fragments: the ban is on the literal, not on this fixture.
_LIVE = "/opt/" + "autobot"
_FIELD_CALLS = 320  # above both FIELD_CALL_FLOOR (200) and FIELD_DEFAULT_FLOOR (300)


def _ssot_source(live_default: bool, calls: int = _FIELD_CALLS) -> str:
    """An ``ssot_config.py`` of *calls* literal-default ``Field`` calls (default: enough to clear both floors)."""
    rows = [f'    f{i}: str = Field(default="v{i}", alias="AUTOBOT_PLANT_{i}")' for i in range(calls)]
    if live_default:
        rows.append(f'    live: str = Field(default="{_LIVE}/x", alias="AUTOBOT_PLANT_LIVE")')
    return "from pydantic import BaseModel, Field\n\n\nclass Config(BaseModel):\n" + "\n".join(rows) + "\n"


def _getenv_sites(drift: bool) -> str:
    """Ten comparable call sites (the floor is 8); the last one disagrees when *drift*."""
    other = "other" if drift else "v9"
    lines = [f'os.getenv("AUTOBOT_PLANT_{i}", "v{i}")' for i in range(9)]
    return "import os\n\n" + "\n".join(lines) + f'\nos.getenv("AUTOBOT_PLANT_9", "{other}")\n'


def _fork_sites(fork: bool, reads: int = FORK_READ_FLOOR + 5) -> dict[str, str]:
    """*reads* literal-fallback env reads clearing ``FORK_READ_FLOOR``; with *fork*, one var gets a second fallback."""
    lines = [f'os.getenv("AUTOBOT_PLANT_{i}", "v{i}")' for i in range(reads)]
    files = {"plant.py": "import os\n\n" + "\n".join(lines) + "\n"}
    # A listed fork that stops forking is itself a finding, so a clean tree must still fork every listed var.
    for suffix, fallback in (("a", "x"), ("b", "y")):
        known = [f'os.getenv("{name}", "{fallback}")' for name in sorted(KNOWN_ENV_FORKS)]
        files[f"known_{suffix}.py"] = "import os\n\n" + "\n".join(known) + "\n"
    if fork:
        files["other.py"] = 'import os\n\nos.getenv("AUTOBOT_PLANT_0", "forked")\n'
    return files


def _repo(root: Path, ssot: str | None, *, fillers: int = 0, sites: str | None = None) -> Path:
    """A tracked throwaway repository: the seeded checkers, *ssot*, and optional bulk."""
    root.mkdir(parents=True, exist_ok=True)
    make_repo(root)
    _seed(root)
    # ``registry_defaults`` imports the env registry modules, and ``_seed`` copies only paths.py.
    for registry in sorted((_REPO_ROOT / "autobot_shared").glob("env_registry*.py")):
        shutil.copy2(registry, root / "autobot_shared" / registry.name)
    if ssot is not None:
        (root / "autobot_shared" / "ssot_config.py").write_text(ssot, encoding="utf-8")
        # The drift checker also reads the TLS SSOT module (#17312); an empty one adds no defaults.
        (root / "autobot_shared" / "ssot_tls.py").write_text("", encoding="utf-8")
        # The env-fork sweep reads all three SSOT modules (#19215); an empty one adds no constants.
        (root / "autobot_shared" / "ssot_constants.py").write_text("", encoding="utf-8")
    if sites is not None:
        (root / "autobot-backend").mkdir()
        (root / "autobot-backend" / "plant.py").write_text(sites, encoding="utf-8")
    bulk = root / "bulk"
    bulk.mkdir()
    for i in range(fillers):
        (bulk / f"m{i}.py").write_text("X = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    return root


def _verdict_repo(root: Path, checker: str, *, planted: bool) -> Path:
    """A repository clearing every floor, so the checker reaches a real verdict: 1 planted, 0 clean."""
    if checker == "check_env_forks.py":
        repo = _repo(root, _ssot_source(False))
        for name, text in _fork_sites(planted).items():
            (repo / "autobot-backend").mkdir(exist_ok=True)
            (repo / "autobot-backend" / name).write_text(text, encoding="utf-8")
        _git(repo, "add", "-A")
        return repo
    if checker == "check_field_defaults.py":
        return _repo(root, _ssot_source(planted))
    return _repo(root, _ssot_source(False), fillers=PY_FLOOR, sites=_getenv_sites(planted))


@pytest.mark.parametrize(("planted", "expected"), [(True, 1), (False, 0)])
@pytest.mark.parametrize("checker", _CHECKERS)
def test_the_checker_answers_the_same_from_a_subdirectory(
    tmp_path: Path, checker: str, planted: bool, expected: int
) -> None:
    """AC1 on a real verdict: a root taken from the cwd would name ``tools/``, not a toplevel, and exit 2."""
    repo = _verdict_repo(tmp_path / "r", checker, planted=planted)
    script = repo / "tools" / "lint" / checker
    runs = [
        subprocess.run(  # nosec B603  # fixed argv, no shell
            [sys.executable, str(script)],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**isolated_git_env(), "PYTHONPATH": str(_REPO_ROOT)},
        )
        for cwd in (repo, repo / "tools")
    ]

    assert runs[0].returncode == runs[1].returncode == expected, runs[0].stderr + runs[1].stderr
    assert (runs[0].stdout, runs[0].stderr) == (runs[1].stdout, runs[1].stderr)


@pytest.mark.parametrize("checker", _CHECKERS)
def test_a_non_git_root_exits_two(tmp_path: Path, checker: str) -> None:
    _seed(tmp_path)

    result = _run_isolated(tmp_path, checker)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "cannot anchor the scan" in result.stderr


@pytest.mark.parametrize("checker", _CHECKERS)
def test_a_repository_without_ssot_config_exits_two(tmp_path: Path, checker: str) -> None:
    repo = _repo(tmp_path / "r", None)

    result = _run_isolated(repo, checker)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "ssot_config.py is not in" in result.stderr


@pytest.mark.parametrize(
    ("checker", "calls", "fillers", "floor_text"),
    [
        # field_defaults: 5 Field calls against FIELD_CALL_FLOOR (200); it has no file floor.
        ("check_field_defaults.py", 5, 0, "floor is 200"),
        # getenv: PY_FLOOR files and 320 field defaults both clear, zero comparable
        # pairs against GETENV_CALL_FLOOR (8) is what is left to refuse.
        ("check_getenv_ssot_drift.py", _FIELD_CALLS, PY_FLOOR, "floor is 8"),
        # env-forks: no literal-fallback reads against FORK_READ_FLOOR.
        ("check_env_forks.py", 5, 0, f"env fallback read(s); floor is {FORK_READ_FLOOR}"),
    ],
)
def test_a_population_below_the_checkers_own_floor_exits_two(
    tmp_path: Path, checker: str, calls: int, fillers: int, floor_text: str
) -> None:
    result = _run_isolated(_repo(tmp_path / "r", _ssot_source(False, calls), fillers=fillers), checker)

    assert result.returncode == 2, result.stdout + result.stderr
    assert floor_text in result.stderr and "FIX THE SWEEP" in result.stderr, result.stderr


@pytest.mark.parametrize(("live_default", "expected"), [(True, 1), (False, 0)])
def test_a_planted_live_install_field_default_exits_one(tmp_path: Path, live_default: bool, expected: int) -> None:
    repo = _repo(tmp_path / "r", _ssot_source(live_default))

    result = _run_isolated(repo, "check_field_defaults.py")

    assert result.returncode == expected, result.stdout + result.stderr
    assert ("freeze the live install path" in result.stderr) is live_default


@pytest.mark.parametrize(("drift", "expected"), [(True, 1), (False, 0)])
def test_a_planted_getenv_drift_exits_one(tmp_path: Path, drift: bool, expected: int) -> None:
    repo = _repo(tmp_path / "r", _ssot_source(False), fillers=PY_FLOOR, sites=_getenv_sites(drift))

    result = _run_isolated(repo, "check_getenv_ssot_drift.py")

    assert result.returncode == expected, result.stdout + result.stderr
    assert ("disagrees with ssot_config" in result.stderr) is drift


def test_a_missing_tls_ssot_source_is_a_loud_refusal(tmp_path: Path) -> None:
    """The drift checker never skips an SSOT field source it cannot find (#17312)."""
    repo = _repo(tmp_path / "no_tls", _ssot_source(False), fillers=PY_FLOOR, sites=_getenv_sites(False))
    (repo / "autobot_shared" / "ssot_tls.py").unlink()
    _git(repo, "add", "-A")
    result = _run_isolated(repo, "check_getenv_ssot_drift.py")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "ssot_tls.py is not in" in result.stderr


@pytest.mark.parametrize(("fork", "expected"), [(True, 1), (False, 0)])
def test_a_planted_env_fork_exits_one(tmp_path: Path, fork: bool, expected: int) -> None:
    """The sweep's own verdict, reached with the floor met -- and the drift hook untouched by it (#19215)."""
    repo = _verdict_repo(tmp_path / "r", "check_env_forks.py", planted=fork)

    result = _run_isolated(repo, "check_env_forks.py")

    assert result.returncode == expected, result.stdout + result.stderr
    assert ("AUTOBOT_PLANT_0" in result.stderr) is fork
    assert ("differing fallbacks" in result.stderr) is fork
    assert _run_isolated(repo, "check_getenv_ssot_drift.py").returncode != 1  # the drift verdict is its own


def test_an_env_fork_repo_without_the_ssot_constants_source_exits_two(tmp_path: Path) -> None:
    repo = _verdict_repo(tmp_path / "r", "check_env_forks.py", planted=False)
    (repo / "autobot_shared" / "ssot_constants.py").unlink()
    _git(repo, "add", "-A")

    result = _run_isolated(repo, "check_env_forks.py")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "ssot_constants.py is not in" in result.stderr and "Traceback" not in result.stderr
