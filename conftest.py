# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Root conftest.py — adds worktree root to sys.path so that tools.lint.* is importable.

tools/ is a namespace package (no __init__.py); it lives at the repo root alongside
autobot-backend/, autobot-frontend/, etc. pytest.ini's pythonpath directive
adds the root but importlib mode requires explicit path insertion for namespace packages.
Issue: #7458
"""

import sys
from pathlib import Path

# Ensure repo root is first on sys.path so `tools.lint.canonical.*` resolves.
_REPO_ROOT = str(Path(__file__).parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Repo-wide sys.modules leak guard (#13337). Declared here — the rootdir
# conftest is the only conftest where ``pytest_plugins`` is still legal in
# pytest >= 9 — and loaded after the sys.path insert above, so ``repo_tests``
# resolves. The plugin registers before any other conftest, which is what lets
# it attribute each one's sys.modules delta.
pytest_plugins = ["repo_tests.sys_modules_leak_guard"]
