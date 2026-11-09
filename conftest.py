# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Root conftest.py — adds worktree root to sys.path so that tools.lint.* is importable.

tools/ is a namespace package (no __init__.py); it lives at the repo root alongside
autobot-backend/, autobot-frontend/, etc. pytest.ini's pythonpath directive
adds the root but importlib mode requires explicit path insertion for namespace packages.
Issue: #7458
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure repo root is first on sys.path so `tools.lint.canonical.*` resolves.
_REPO_ROOT = str(Path(__file__).parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# The test profile serves the frontend from the Vite dev server (#19326), whatever environment a
# test module runs under; test modules read config.frontend_url at import.
os.environ.setdefault("AUTOBOT_FRONTEND_SERVED_BY", "vite")

# No test run writes logs into the source tree or the user's state dir (#20894): the test route of
# autobot_shared/log_dir.py is this one temp log directory for the whole run, inherited by every
# subprocess a test starts (repo_tests/_reach_base.py base checkouts included). The directory is
# created here, at session start; the app modules a test imports create nothing (first-write handler).
# Created only when the run does not already inherit one, so an xdist worker or a nested pytest
# never leaves an orphan temp directory behind.
_RUN_LOGS_DIR = None if os.environ.get("AUTOBOT_LOGS_DIR") else tempfile.mkdtemp(prefix="autobot-logs-")
if _RUN_LOGS_DIR:
    os.environ["AUTOBOT_LOGS_DIR"] = _RUN_LOGS_DIR


def pytest_sessionfinish(session, exitstatus) -> None:
    """Remove the run's temp log directory (#20894); xdist workers share the controller's via env, so
    only the process that created it removes it."""
    if _RUN_LOGS_DIR and not os.environ.get("PYTEST_XDIST_WORKER"):
        shutil.rmtree(_RUN_LOGS_DIR, ignore_errors=True)


# Repo-wide sys.modules leak guard (#13337). Declared here — the rootdir
# conftest is the only conftest where ``pytest_plugins`` is still legal in
# pytest >= 9 — and loaded after the sys.path insert above, so ``repo_tests``
# resolves. The plugin registers before any other conftest, which is what lets
# it attribute each one's sys.modules delta.
# Dependency-floor banner (#15091). Same placement rationale as the leak guard:
# declared here because the rootdir conftest is the only legal home, and it is
# the one file that runs before every local pytest invocation, including the
# bare `pytest` runs that never touch scripts/pr-preflight.sh.
# Empty HuggingFace cache per session (#16994): first, so it is set before any
# plugin or test module imports huggingface_hub.
# SSOT singleton restore (#19232): a test that clears get_config() leaves it as it found it,
# so import-time bindings to the singleton (models/settings.py's aliases) never go stale.
# Machine-wide queue for a big local run (#20518), so a run from any directory under this root queues.
pytest_plugins = [
    "repo_tests.hermetic_model_cache",
    "repo_tests.machine_slot",
    "repo_tests.sys_modules_leak_guard",
    "repo_tests.dependency_floor_banner",
    "repo_tests.ssot_config_singleton_guard",
]
