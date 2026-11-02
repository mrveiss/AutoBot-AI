# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The indexing watchdog limits come from the environment and cannot crash the indexer (#18057)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from api.codebase_analytics.indexing_executor import _bounded_seconds

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

# The names ``_wait_with_watchdog`` reads, in the module it reads them from.
READ_WATCHDOG_LIMITS = """
import json
from api.codebase_analytics import subprocess_runner as r
print(json.dumps([r._SUBPROCESS_HARD_TIMEOUT, r._SUBPROCESS_PROGRESS_TIMEOUT, r._SUBPROCESS_WATCHDOG_INTERVAL]))
"""


def _limits_with_env(**env):
    """Import the watchdog in a fresh process, since the limits are read at import."""
    result = subprocess.run(
        [sys.executable, "-c", READ_WATCHDOG_LIMITS],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=BACKEND_ROOT,
        env={**os.environ, "PYTHONPATH": f"{BACKEND_ROOT}{os.pathsep}{REPO_ROOT}", **env},
        timeout=120,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_env_override_reaches_the_watchdog_module():
    assert _limits_with_env(
        AUTOBOT_INDEXING_HARD_TIMEOUT="7200",
        AUTOBOT_INDEXING_PROGRESS_TIMEOUT="900",
        AUTOBOT_INDEXING_WATCHDOG_INTERVAL="10",
    ) == [7200, 900, 10]


def test_unparseable_env_keeps_the_default_instead_of_failing_the_import():
    assert _limits_with_env(AUTOBOT_INDEXING_HARD_TIMEOUT="soon")[0] == 1800


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("300", 300), ("1", 30), ("999999", 14400), ("soon", 300), ("", 300)],
)
def test_bounded_seconds(raw, expected):
    assert _bounded_seconds("AUTOBOT_X", raw, 300, 30, 14400) == expected
