# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`git_mcp` must operate on the repository it validated, not the ambient one (#15991).

`_run_git_process` ran `asyncio.create_subprocess_exec` with no `env=`, so it
inherited `GIT_DIR` whole. **`GIT_DIR` outranks both the `-C repo_path` in the
argv and the `cwd=`**, which is the whole finding:

    git -C /a ls-files                     -> /a's files
    GIT_DIR=/b/.git git -C /a ls-files     -> /b's files
    cd /a && GIT_DIR=/b/.git git -C /a …   -> /b's files

So `is_repository_allowed` validated a path git then did not operate on. The
path was not unused — it is used twice — and one environment variable outranks
both, which is why no additional path validation could have closed it.

The guard that catches this shape (`check_git_toplevel_env_scrubbed`) covers
`autobot-backend/`; verified by planting a tracked probe there and watching it
report. What it cannot see is argv reaching the call through a **variable**
(`create_subprocess_exec(*cmd)`), which its own docstring names as *"the gap
most likely to be reached by accident, since it is an ordinary refactor rather
than an evasion."* Documented precisely, and nothing detected this instance.
"""

from __future__ import annotations

import subprocess  # nosec B404  # fixed argv, no shell, test fixtures only
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env


def _repo(where: Path, filename: str) -> Path:
    """A throwaway repository holding one tracked file, built with a scrubbed env.

    Scrubbed deliberately: a fixture that demonstrates a `GIT_DIR` hazard must
    not be subject to it. Built unscrubbed, `git init` under an inherited
    `GIT_DIR` operates on the real repository and stages the decoy into it.
    """
    where.mkdir(parents=True, exist_ok=True)
    env = scrubbed_git_env()
    subprocess.run(["git", "-C", str(where), "init", "-q"], check=True, env=env)  # nosec B603 B607
    (where / filename).write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(where), "add", filename], check=True, env=env)  # nosec B603 B607
    return where


@pytest.mark.asyncio
async def test_the_endpoint_reads_the_validated_repository_not_git_dir(tmp_path, monkeypatch):
    """With `GIT_DIR` pointed elsewhere, the command still answers about `repo_path`."""
    from api import git_mcp

    validated = _repo(tmp_path / "validated", "mine.txt")
    decoy = _repo(tmp_path / "decoy", "theirs.txt")
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))

    result = await git_mcp._run_git_process(["git", "-C", str(validated), "ls-files"], str(validated), 30)

    assert result["success"], result["stderr"]
    assert "mine.txt" in result["stdout"]
    assert "theirs.txt" not in result["stdout"], (
        "the endpoint enumerated the repository GIT_DIR named, not the one its "
        "containment check validated"
    )


@pytest.mark.asyncio
async def test_an_unscrubbed_call_does_follow_git_dir_here(tmp_path, monkeypatch):
    """The contrast: this machine must be able to exhibit the hazard.

    Without it, the assertion above passes on a platform or git version where
    `GIT_DIR` never mattered, and credits the scrub for an absence it did not
    cause.
    """
    validated = _repo(tmp_path / "validated", "mine.txt")
    decoy = _repo(tmp_path / "decoy", "theirs.txt")
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))

    raw = subprocess.run(  # nosec B603 B607  # deliberately unscrubbed: that is the point
        ["git", "-C", str(validated), "ls-files"],
        cwd=str(validated),
        capture_output=True,
        text=True,
        check=False,
    )

    assert "theirs.txt" in raw.stdout, (
        "an unscrubbed git did NOT follow GIT_DIR here, so this machine cannot "
        "demonstrate the hazard and the test above is not evidence of the scrub"
    )


def test_the_helper_refuses_a_caller_supplied_environment():
    """`start_git` rejects `env=`, so the scrub is not a parameter to omit.

    An optional scrub is off by default at every call site that forgets it —
    the shape of #15930 and #15931. This asserts the helper forbids the omission
    rather than merely defaulting to the safe value.
    """
    from autobot_shared.git_probe import _reject_env

    with pytest.raises((ValueError, TypeError)):
        _reject_env({"env": {"GIT_DIR": "/anywhere"}})
