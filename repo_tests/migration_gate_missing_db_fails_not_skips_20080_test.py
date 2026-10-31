# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A missing admin URL turns the Migration Gate red instead of skipping its tests (#20080).

`requires_postgres` skipped every test under `autobot-backend/tests/migrations/` when
`AUTOBOT_MIGRATION_TEST_ADMIN_URL` was missing, so the job stayed green on nothing. The gate now sets
`AUTOBOT_MIGRATION_TEST_REQUIRE_DB`, which turns that one skip into a failure. Other skips (a module
`importorskip`, an unrelated `skipif`) are untouched: only the database-missing path is converted, because
it is the only one that goes through `requires_postgres` / `fresh_db_url`. A developer without Postgres and
without the marker still gets the skip.

The conftest is copied next to planted tests in a temp dir and run in a subprocess pytest.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from repo_tests._paths import repo_root

_CONFTEST = Path("autobot-backend/tests/migrations/conftest.py")
_WORKFLOW = Path(".github/workflows/migration-gate.yml")
_ADMIN = "AUTOBOT_MIGRATION_TEST_ADMIN_URL"
_REQUIRE = "AUTOBOT_MIGRATION_TEST_REQUIRE_DB"

_PLANTED = """
import pytest
from conftest import requires_postgres


@requires_postgres
def test_marker_path():
    pass


async def test_fixture_path(fresh_db_url):
    pass


@pytest.mark.skip(reason="unrelated")
def test_unrelated_skip():
    pass
"""


def _run(tmp_path: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    shutil.copy(repo_root() / _CONFTEST, tmp_path / "conftest.py")
    (tmp_path / "test_planted.py").write_text(_PLANTED, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in (_ADMIN, _REQUIRE)}
    env.update(extra_env)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-o",
            "asyncio_mode=auto",
            "-rs",
            "-q",
            "test_planted.py",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_marker_set_and_url_missing_fails_the_run(tmp_path: Path) -> None:
    proc = _run(tmp_path, {_REQUIRE: "1"})
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert "2 errors" in out, out  # both database paths error in setup rather than skip
    assert "1 skipped" in out, out  # the unrelated skip is still a skip: only the database skip is converted


def test_no_marker_keeps_the_skip_for_developers(tmp_path: Path) -> None:
    proc = _run(tmp_path, {})
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "3 skipped" in out, out


def test_the_gate_step_that_sets_the_admin_url_also_sets_the_marker() -> None:
    wf = yaml.safe_load((repo_root() / _WORKFLOW).read_text(encoding="utf-8"))
    steps = [s for job in wf["jobs"].values() for s in job.get("steps", []) if _ADMIN in (s.get("env") or {})]
    assert steps, f"no gate step sets {_ADMIN}: the pytest step moved, so this guard reads nothing"
    for step in steps:
        assert str(step["env"].get(_REQUIRE)) == "1", f"step {step.get('name')!r} sets the URL but not {_REQUIRE}"
