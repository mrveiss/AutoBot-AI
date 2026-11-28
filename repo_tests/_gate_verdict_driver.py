# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The one driver of `.github/actions/gate-verdict/verdict.sh`, shared by the guards that judge it (#18208, #20552).

The script is read from the environment, so a test drives the same code the composite action runs.
Two guards need it: `gate_verdict_18208_test.py` (every branch of the script) and
`short_check_stages_ci_20552_test.py` (what the real gates in ci.yml feed it).
"""

import subprocess

import yaml
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


CANCEL_ACTION = repo_root() / ".github" / "actions" / "cancel-run-on-cancelled-upstream" / "action.yml"
#: Where the action's shell leaves the decision and starts calling the API; nothing past it is run.
_FIRST_API_CALL = "timed_out=$("


def cancel_decision_script() -> str:
    """The cancel action's own `run:` block, cut before its first API call, ending in a marker.

    The `case` on the results list is the decision; what follows it needs `gh` and the network and
    is never executed here. The marker is printed only if the block reached the cancel path.
    """
    steps = yaml.safe_load(CANCEL_ACTION.read_text(encoding="utf-8"))["runs"]["steps"]
    head, found, _ = steps[0]["run"].partition(_FIRST_API_CALL)
    assert found, "the cancel action no longer has the API call this driver cuts before"
    return head + "echo DECISION=cancel\n"


def run_cancel_decision(results: str) -> tuple[int, str]:
    """`(exit code, output)` of the cancel action's decision for a space-separated `results` list."""
    env = {"PATH": "/usr/bin:/bin", "RESULTS": results, "WAIT_SECONDS": "0"}
    script = cancel_decision_script()
    proc = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout + proc.stderr
