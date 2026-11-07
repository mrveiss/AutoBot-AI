# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A transient GitHub error does not turn a cancelled gate into a failed check (#20067).

A gate whose upstream was cancelled force-cancels its own run. On a 502 that call died under `set -e`
and the gate read as failed, though no test had. This runs the shipped step against a fake `gh`.
"""

from __future__ import annotations

import os
import subprocess

import yaml
from repo_tests._paths import repo_root

_ACTION = repo_root() / ".github" / "actions" / "cancel-run-on-cancelled-upstream" / "action.yml"


def _run(tmp_path, gh_fails: int, results: str = "cancelled success") -> subprocess.CompletedProcess:
    script = yaml.safe_load(_ACTION.read_text(encoding="utf-8"))["runs"]["steps"][0]["run"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    count = tmp_path / "count"
    calls = tmp_path / "calls"
    gh = bin_dir / "gh"
    gh.write_text(
        f"""#!/bin/bash
echo "$*" >> {calls}
n=$(cat {count} 2>/dev/null || echo 0); echo $((n + 1)) > {count}
if [ "$n" -lt {gh_fails} ]; then echo "gh: Server Error (HTTP 502)" >&2; exit 1; fi
""",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    sleeper = bin_dir / "sleep"
    sleeper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sleeper.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RESULTS": results,
        "WAIT_SECONDS": "0",
        "REPO": "o/r",
        "RUN_ID": "1",
    }
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, cwd=tmp_path, check=False)


def _force_cancels(tmp_path) -> int:
    return (tmp_path / "calls").read_text(encoding="utf-8").count("force-cancel")


def test_a_transient_error_is_retried_until_the_cancel_is_sent(tmp_path) -> None:
    result = _run(tmp_path, gh_fails=2)
    assert _force_cancels(tmp_path) == 1, result.stdout + result.stderr
    assert "timed out" not in result.stdout, "a retry warning was read as a timed-out job"
    assert "did not stop this job" in result.stdout, "the fake cancel stops nothing, so it must reach the wait"


def test_github_staying_down_still_fails_closed_without_cancelling(tmp_path) -> None:
    result = _run(tmp_path, gh_fails=100)
    assert result.returncode != 0
    assert _force_cancels(tmp_path) == 0
    assert "attempt 4 failed" in result.stderr


def test_contrast_no_cancelled_upstream_touches_nothing(tmp_path) -> None:
    result = _run(tmp_path, gh_fails=0, results="success success")
    assert result.returncode == 0 and not (tmp_path / "calls").exists()
