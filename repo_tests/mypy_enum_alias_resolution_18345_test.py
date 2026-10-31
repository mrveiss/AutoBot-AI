# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``X = Severity`` stays a type under the repo's mypy config, from any cwd (#18345).

The backend mypy run is rooted in ``autobot-backend/``. There ``autobot_shared`` did not resolve,
``ignore_missing_imports`` turned ``Severity`` into ``Any``, and every ``X = Severity`` alias then read
as a variable: ``Variable "X" is not valid as a type [valid-type]``, and each annotated field degraded
to ``X?``. ``mypy_path = "$MYPY_CONFIG_FILE_DIR"`` makes the package resolve whatever the cwd is.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from repo_tests._paths import repo_root

_FIXTURE = """\
from autobot_shared.status_enums import Severity

PerformanceSeverity = Severity


def level(severity: PerformanceSeverity) -> str:
    return severity.value
"""


def _mypy(cwd: Path, config: Path) -> str:
    (cwd / "alias.py").write_text(_FIXTURE, encoding="utf-8")
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            f"--config-file={config}",
            "--follow-imports=silent",
            f"--cache-dir={cwd / 'cache'}",
            "alias.py",
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return run.stdout + run.stderr


def test_an_enum_alias_is_a_valid_type_from_a_backend_rooted_run(tmp_path: Path) -> None:
    out = _mypy(tmp_path, repo_root() / "pyproject.toml")
    assert "valid-type" not in out and "has no attribute" not in out, f"#18345: {out}"


def test_without_the_path_the_same_alias_fails_so_the_check_can_see_it(tmp_path: Path) -> None:
    config = tmp_path / "no_path.toml"
    config.write_text("[tool.mypy]\nignore_missing_imports = true\n", encoding="utf-8")
    assert "valid-type" in _mypy(tmp_path, config)


def test_the_repo_config_declares_the_path() -> None:
    cfg = tomllib.loads((repo_root() / "pyproject.toml").read_text(encoding="utf-8"))
    assert cfg["tool"]["mypy"]["mypy_path"] == "$MYPY_CONFIG_FILE_DIR"
