# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every Python service unit must be given AUTOBOT_LOGS_DIR (#20894).

Unset, `autobot_shared.log_dir.resolve_logs_dir` falls back to `$XDG_STATE_HOME/autobot/logs`, so a unit
that does not set it moves its logs on the next deploy. A Python service is a systemd unit template whose
`ExecStart=` runs python, uvicorn or celery (every such service reaches the resolver through
`logging_manager` / `ssot_config`). It passes when the unit itself, or an env template beside it, sets the
variable.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests.python_filter_covers_its_guards_test import _filter_patterns, _is_covered

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_VAR = "AUTOBOT_LOGS_DIR"
_PYTHON_EXEC = re.compile(r"^ExecStart=.*(python|uvicorn|celery)", re.MULTILINE)
_SET = re.compile(rf"^(Environment=\"?)?{_VAR}=", re.MULTILINE)
# Concrete template directories (not root-relative `*.service` sweeps) so the python filter in
# .github/filters/python-paths.yml names every tree this guard reads; a unit outside them fails
# `test_narrowed_dirs_find_every_unit_the_whole_tree_sweep_finds` instead of going un-run.
_UNIT_DIRS = (
    "autobot-slm-backend/ansible/roles/*/templates",
    "autobot-slm-backend/ansible/templates/systemd",
    "autobot-infrastructure/*/templates",
    "scripts/systemd",
)
_UNIT_SUFFIXES = (".service", ".service.j2")
_ENV_SUFFIXES = (".env", ".env.j2")
_MIN_PYTHON_UNITS = 15  # live count when written: 15; a drop below this means discovery broke


def _python_units(root: Path) -> list[str]:
    units = tracked_paths(root, *(f"{d}/*{suffix}" for d in _UNIT_DIRS for suffix in _UNIT_SUFFIXES))
    return sorted(p for p in units if _PYTHON_EXEC.search((root / p).read_text(encoding="utf-8")))


def _env_beside(root: Path, unit: str) -> list[str]:
    templates = (root / unit).parent
    return [str(p.relative_to(root)) for p in templates.iterdir() if p.name.endswith(_ENV_SUFFIXES)]


def _unset(root: Path, units: list[str]) -> list[str]:
    """Units that neither set the variable themselves nor have an env template beside them that does."""
    missing: list[str] = []
    for unit in units:
        files = [unit, *_env_beside(root, unit)]
        if not any(_SET.search((root / f).read_text(encoding="utf-8")) for f in files):
            missing.append(unit)
    return missing


def test_every_python_service_unit_sets_the_log_dir() -> None:
    units = _python_units(_ROOT)
    assert len(units) >= _MIN_PYTHON_UNITS, f"discovery found only {len(units)} python units"
    missing = _unset(_ROOT, units)
    assert not missing, f"unit(s) leave {_VAR} unset, so their logs move to the XDG state dir: {missing}"


def _swept_files(root: Path) -> list[str]:
    """Every unit and env template the sweep reads: the discovered units plus the env templates beside them."""
    files = set(_python_units(root))
    files |= {e for u in list(files) for e in _env_beside(root, u)}
    return sorted(files)


def test_every_swept_file_is_under_the_python_filter() -> None:
    """The guard runs only when the python filter fires, so every file it reads must match a filter pattern.

    A new template directory, or a unit moved out of the listed ones, fails here rather than silently
    leaving the guard un-run when that tree changes. Replaces recording this test as uncovered debt.
    """
    patterns = _filter_patterns()
    outside = [f for f in _swept_files(_ROOT) if not _is_covered(f, patterns)]
    assert not outside, f"swept file(s) outside .github/filters/python-paths.yml `python`: {outside}"


def test_narrowed_dirs_find_every_unit_the_whole_tree_sweep_finds() -> None:
    """Count equality: discovery over the concrete dirs equals the old root-relative whole-tree sweep (15)."""
    everywhere = sorted(
        p
        for p in tracked_paths(_ROOT, *(f"*{suffix}" for suffix in _UNIT_SUFFIXES))
        if ("/templates/" in p or p.startswith("scripts/systemd"))
        and _PYTHON_EXEC.search((_ROOT / p).read_text(encoding="utf-8"))
    )
    narrowed = _python_units(_ROOT)
    assert narrowed == everywhere, f"missed by the narrowed dirs: {sorted(set(everywhere) - set(narrowed))}"
    assert len(narrowed) >= _MIN_PYTHON_UNITS


def test_control_an_uncovered_dir_is_reported() -> None:
    """Control: a unit in a directory no pattern names is flagged, one in a named directory is not."""
    patterns = _filter_patterns()
    # A plain `.service`: the filter's `**/*.j2` (#20884) covers every `.j2` anywhere, so only a non-`.j2` path
    # can sit in a directory no pattern names.
    assert not _is_covered("some/new/dir/svc.service", patterns)
    assert _is_covered("autobot-slm-backend/ansible/roles/redis/templates/svc.service.j2", patterns)


def test_control_a_unit_without_the_variable_is_caught(tmp_path: Path) -> None:
    """Control: the detector reports a unit that omits the variable and passes one that sets it."""
    bad = tmp_path / "roles" / "bad" / "templates"
    bad.mkdir(parents=True)
    (bad / "svc.service.j2").write_text("[Service]\nExecStart=/x/venv/bin/uvicorn main:app\n", encoding="utf-8")
    (bad / "svc.env.j2").write_text("REDIS_HOST=h\n", encoding="utf-8")
    assert _unset(tmp_path, ["roles/bad/templates/svc.service.j2"]) == ["roles/bad/templates/svc.service.j2"]
    (bad / "svc.env.j2").write_text("REDIS_HOST=h\nAUTOBOT_LOGS_DIR={{ d }}\n", encoding="utf-8")
    assert _unset(tmp_path, ["roles/bad/templates/svc.service.j2"]) == []
    (bad / "svc.env.j2").write_text("REDIS_HOST=h\n", encoding="utf-8")
    (bad / "svc.service.j2").write_text(
        '[Service]\nEnvironment="AUTOBOT_LOGS_DIR={{ d }}"\nExecStart=/x/python m\n', encoding="utf-8"
    )
    assert _unset(tmp_path, ["roles/bad/templates/svc.service.j2"]) == []
