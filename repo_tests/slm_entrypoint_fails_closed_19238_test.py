# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""docker/slm/entrypoint.sh stops on a failed migration or import probe (#19238).

Each step is piped to `tee`, and without `pipefail` a pipeline's status was tee's: a failed
migration skipped its retry and FATAL branch and the container exec'd uvicorn on an unmigrated
database. These run the real entrypoint with a stub `python3` on PATH and an `exec` target that
records whether it was reached.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404  # fixed argv, no shell
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_ENTRYPOINT = repo_root() / "docker" / "slm" / "entrypoint.sh"


def _run(tmp_path: Path, *, migration_rc: int, probe_rc: int) -> tuple[subprocess.CompletedProcess, Path]:
    (tmp_path / "app" / "autobot-slm-backend").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "python3"
    stub.write_text(
        "#!/bin/bash\n" f'case "$1" in -m) exit {migration_rc} ;; -c) exit {probe_rc} ;; esac\n' "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    (bin_dir / "sleep").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (bin_dir / "sleep").chmod(0o755)
    marker = tmp_path / "reached_exec"
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "SLM_APP_DIR": str(tmp_path / "app")}
    done = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["bash", str(_ENTRYPOINT), "touch", str(marker)], env=env, capture_output=True, text=True, timeout=60
    )
    return done, marker


def test_a_healthy_start_reaches_exec(tmp_path):
    done, marker = _run(tmp_path, migration_rc=0, probe_rc=0)
    assert done.returncode == 0 and marker.exists(), done.stdout + done.stderr


def test_a_failing_migration_exits_nonzero_and_never_starts_the_app(tmp_path):
    done, marker = _run(tmp_path, migration_rc=1, probe_rc=0)
    assert done.returncode != 0 and not marker.exists()
    assert "FATAL: Migration failed after retry" in done.stdout
    assert "Migrations complete." not in done.stdout


def test_a_failing_import_probe_exits_nonzero_and_never_starts_the_app(tmp_path):
    done, marker = _run(tmp_path, migration_rc=0, probe_rc=1)
    assert done.returncode != 0 and not marker.exists()
    assert "Migrations complete." in done.stdout


@pytest.mark.parametrize("probe_rc", [0])
def test_the_startup_log_lands_under_the_app_dir(tmp_path, probe_rc):
    _run(tmp_path, migration_rc=0, probe_rc=probe_rc)
    assert (tmp_path / "app" / "logs" / "slm-startup.log").is_file()
