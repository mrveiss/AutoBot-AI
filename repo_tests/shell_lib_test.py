# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run the shell-library test suites under pytest (#13149).

``scripts/lib/`` ships bash test suites that nothing executed. CI's Python suite
collects ``autobot-backend autobot_shared autobot-tts-worker repo_tests tools``,
and no workflow runs ``bash scripts/lib/*_test.sh``, so
``branch-guards_test.sh`` — the regression suite for the #10035
branch-deletion race — had been dormant since it was written.

Wrapping them here rather than adding a workflow step keeps them in the suite
that already runs on every PR. ``repo_tests`` is used deliberately: ``scripts/``
is *not* in CI's collection list either, so a wrapper placed next to the shell
files would have been just as dormant as the files it runs.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import project_root

SHELL_SUITES = [
    "scripts/lib/branch-guards_test.sh",
    "scripts/lib/project_root_test.sh",
]


@pytest.mark.parametrize("suite", SHELL_SUITES)
def test_shell_suite_passes(suite: str) -> None:
    """Each bash suite must exit 0, with its own output on failure."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash unavailable")

    script = project_root() / suite
    assert script.exists(), f"missing shell suite: {suite}"

    result = subprocess.run(
        [bash, str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(project_root()),
    )

    assert result.returncode == 0, (
        f"{suite} failed (exit {result.returncode})\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


def test_every_shell_suite_is_registered() -> None:
    """A new scripts/lib/*_test.sh must be added above, or it silently never runs.

    This is the guard for the failure this module exists to fix: the suite was
    not broken, it was simply never invoked by anything.
    """
    lib = project_root() / "scripts" / "lib"
    on_disk = {f"scripts/lib/{p.name}" for p in lib.glob("*_test.sh")}

    assert on_disk == set(SHELL_SUITES), (
        "shell test suites on disk do not match the registered list — "
        f"unregistered: {sorted(on_disk - set(SHELL_SUITES))}, "
        f"missing from disk: {sorted(set(SHELL_SUITES) - on_disk)}"
    )
