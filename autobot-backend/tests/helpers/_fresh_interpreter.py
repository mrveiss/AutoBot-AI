# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run a snippet in a FRESH interpreter with the backend import roots set (#21596).

Lazy-import guards must not inspect ``sys.modules`` in-process: by the time a test
runs, earlier tests have cached modules that Python will never re-import, so a
meta-path finder or a presence check proves nothing about a clean import. A fresh
process has nothing cached, so ``sys.modules`` after the import is the complete
set the import reaches.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent

_LEAK_SNIPPET = (
    "import sys; "
    "{statement}; "
    "blocked = {blocked!r}; "
    "leaked = sorted(m for m in sys.modules "
    "if any(m == b or m.startswith(b + '.') for b in blocked)); "
    "sys.stdout.write('LEAKED:' + ','.join(leaked) if leaked else 'CLEAN')"
)


def run_fresh(script: str, *, timeout: int = 120, inherit_env: bool = True) -> subprocess.CompletedProcess:
    """Run ``script`` via ``python -c`` in a new interpreter (no network, bounded).

    ``inherit_env=False`` runs with ``PYTHONPATH`` as the only variable.
    """
    env = dict(os.environ) if inherit_env else {}
    env["PYTHONPATH"] = f"{_REPO_ROOT}{os.pathsep}{_BACKEND_DIR}"
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_BACKEND_DIR),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )


def assert_import_leaks_nothing(statement: str, blocked: tuple[str, ...]) -> None:
    """Fail if running ``statement`` in a fresh interpreter loads any ``blocked`` name."""
    result = run_fresh(_LEAK_SNIPPET.format(statement=statement, blocked=blocked))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "CLEAN", f"`{statement}` reached a blocked stack: {result.stdout}\n{result.stderr}"
