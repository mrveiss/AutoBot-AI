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
