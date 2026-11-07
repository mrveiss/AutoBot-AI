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

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_VAR = "AUTOBOT_LOGS_DIR"
_PYTHON_EXEC = re.compile(r"^ExecStart=.*(python|uvicorn|celery)", re.MULTILINE)
_SET = re.compile(rf"^(Environment=\"?)?{_VAR}=", re.MULTILINE)
_UNIT_GLOBS = ("*.service", "*.service.j2")
_ENV_GLOBS = ("*.env", "*.env.j2")
_MIN_PYTHON_UNITS = 15  # live count when written: 15; a drop below this means discovery broke


def _python_units(root: Path) -> list[str]:
    units: list[str] = []
    for glob in _UNIT_GLOBS:
        units += [p for p in tracked_paths(root, glob) if "/templates/" in p or p.startswith("scripts/systemd")]
    return sorted(p for p in units if _PYTHON_EXEC.search((root / p).read_text(encoding="utf-8")))


def _env_beside(root: Path, unit: str) -> list[str]:
    templates = (root / unit).parent
    return [str(p.relative_to(root)) for g in _ENV_GLOBS for p in templates.glob(g)]


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
