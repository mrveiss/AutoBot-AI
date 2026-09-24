# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`check-issue-close-refs.sh` refuses distinguishably outside a work tree (#17418).

This script is closure gate 2 (#11599). Its own exit vocabulary:

    0   no forward-tracking references -- closure may proceed
    1   references found -- closure BLOCKED
    2   invocation error

Before #17418 a bare `ROOT=$(git_repo_root)` outside a work tree aborted under
`set -e` with **exit 1 and empty stderr** -- the script's own "closure blocked"
verdict, produced by a run that never looked at anything. A caller reading only
the exit code could not tell a real finding from a script that could not find
the repository.

The exact codes are asserted, never "non-zero": 1 and 2 are both non-zero and
they mean opposite things here, so a `!= 0` assertion passes on the defect.
"""

import os
import pathlib
import subprocess

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "pipeline-scripts" / "check-issue-close-refs.sh"


def _run(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    # GIT_DIR scrubbed (#15246): an ambient GIT_DIR would make a non-repo
    # directory resolve to the real repository and the refusal would never fire,
    # so the test would pass while exercising the opposite condition.
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
    return subprocess.run(
        ["bash", str(_SCRIPT), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_outside_a_work_tree_it_exits_two_not_one(tmp_path: pathlib.Path) -> None:
    """Exit 2, because exit 1 is this script's verdict for a real finding."""
    res = _run(tmp_path, "12345")

    assert res.returncode == 2, (
        f"expected 2 (invocation error), got {res.returncode}. "
        f"1 would be indistinguishable from 'forward-tracking references found'. "
        f"stdout={res.stdout!r} stderr={res.stderr!r}"
    )


def test_the_refusal_says_why(tmp_path: pathlib.Path) -> None:
    """An exit code with empty stderr is what made the old failure undiagnosable."""
    res = _run(tmp_path, "12345")

    assert "not a git repo" in res.stderr, (
        f"the refusal must name its cause; the pre-#17418 abort produced an empty "
        f"stderr, so a caller saw only a bare code. stderr={res.stderr!r}"
    )


def test_usage_error_still_exits_two(tmp_path: pathlib.Path) -> None:
    """Positive control on the OTHER path to 2.

    Without it, a script that exited 2 unconditionally would satisfy both
    assertions above.
    """
    res = _run(tmp_path)

    assert res.returncode == 2
