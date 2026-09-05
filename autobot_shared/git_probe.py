# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run git so that it cannot be run wrong (#15783).

``scrubbed_git_env()`` is the canonical *value*; this module is the canonical
*call*. The difference matters: a helper you must remember to pass is one a
fifth author forgets, and four independent fixes for one defect
(#13882/#13983, #15176, #15245/#15303, #15777) is the evidence that they do.
Here the scrub is not an argument — there is no spelling of these functions
that inherits the ambient git environment.

``argv`` never carries ``"git"``: the subcommand is the first element, so a
call site cannot accidentally address a different binary, and the argv reads
as the git command it is.

Defaults are the shape every converted call site already asked for — captured
output, text mode, UTF-8 — so a conversion drops lines rather than adding
them. Anything unusual still goes through as a keyword.
"""

from __future__ import annotations

import asyncio
import subprocess  # nosec B404  # fixed argv, shell=False, scrubbed env
from pathlib import Path
from typing import Sequence

from autobot_shared.env_utils import env_int
from autobot_shared.paths import scrubbed_git_env

#: Ceiling for a probe that would otherwise hang on a lock or a prompt. Env-var
#: backed rather than literal, per the repository's TTL rule.
GIT_PROBE_TIMEOUT_SECONDS = env_int("AUTOBOT_GIT_PROBE_TIMEOUT_SECONDS", 30)


def _reject_env(kwargs: dict) -> None:
    """An ``env=`` here would be the defect this module exists to remove.

    Refused explicitly rather than left to collide with the scrubbed value as a
    duplicate keyword: the TypeError Python raises for that names the argument
    but not the reason, and a caller who wants extra variables wants them
    *added* to the scrub, which is what ``os.environ`` already gives them.
    """
    if "env" in kwargs:
        raise TypeError("run_git/start_git scrub the environment themselves; passing env= would defeat that (#15783)")


def run_git(
    argv: Sequence[str],
    *,
    cwd: str | Path | None = None,
    timeout: float | None = None,
    check: bool = False,
    **kwargs: object,
) -> subprocess.CompletedProcess:
    """Run ``git <argv>`` synchronously with the git environment scrubbed.

    ``argv`` excludes the ``git`` itself: ``run_git(["log", "-1"])``.
    """
    _reject_env(kwargs)
    options: dict[str, object] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
    }
    options.update(kwargs)
    return subprocess.run(  # nosec B603 B607  # fixed argv, shell=False, scrubbed env
        ["git", *argv],
        cwd=cwd,
        timeout=GIT_PROBE_TIMEOUT_SECONDS if timeout is None else timeout,
        check=check,
        env=scrubbed_git_env(),
        **options,
    )


async def start_git(*argv: str, **kwargs: object) -> asyncio.subprocess.Process:
    """Start ``git <argv>`` asynchronously with the git environment scrubbed.

    Both pipes are captured by default because every call site converted to
    this helper wanted them; ``communicate()`` stays the caller's to await, so
    the streaming shapes are unaffected.
    """
    _reject_env(kwargs)
    options: dict[str, object] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    options.update(kwargs)
    return await asyncio.create_subprocess_exec("git", *argv, env=scrubbed_git_env(), **options)
