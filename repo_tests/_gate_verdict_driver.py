# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The one driver of `.github/actions/gate-verdict/verdict.sh`, shared by the guards that judge it (#18208, #20552).

The script is read from the environment, so a test drives the same code the composite action runs.
Two guards need it: `gate_verdict_18208_test.py` (every branch of the script) and
`short_check_stages_ci_20552_test.py` (what the real gates in ci.yml feed it).
"""

import subprocess

from repo_tests._paths import repo_root

SCRIPT = repo_root() / ".github" / "actions" / "gate-verdict" / "verdict.sh"

BASE = {
    "GATE_CONTEXT": "python-suite",
    "GATE_CHANGES_RESULT": "success",
    "GATE_APPLIES": "true",
    "GATE_WORK_OK": "true",
    "GATE_WORK_DETAIL": "python-shard=success",
    "GATE_EVENT": "pull_request",
    "GATE_DRAFT": "false",
    "GATE_DRAFT_GATED": "true",
}


def run_verdict_env(env: dict) -> subprocess.CompletedProcess:
    """Run the script with exactly `env` (plus PATH): a missing input stays missing."""
    return subprocess.run(
        ["bash", str(SCRIPT)], env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True, check=False
    )


def run_verdict(**override) -> tuple[int, str]:
    """`(exit code, output)` for the BASE inputs with `override` applied."""
    proc = run_verdict_env({**BASE, **override})
    return proc.returncode, proc.stdout + proc.stderr
