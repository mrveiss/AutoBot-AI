# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Import modules in a fresh interpreter whose ``config`` is a ``MagicMock`` (#19288).

Shared by the autobot_shared and SLM-backend halves of the #19288 guard. A fresh interpreter, because
the sweep needs a ``sys.modules`` and a ``LoggingManager`` cache that no earlier test has populated
with real config. ``sys.modules["config"] = MagicMock()`` is what the SLM conftest's
``_stub("config")`` installs, so every ``config_manager.get_nested(...)`` returns a ``MagicMock``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from repo_tests._paths import repo_root

REPO_ROOT = repo_root()

_SWEEP = """
import importlib, json, pkgutil, sys
from unittest.mock import MagicMock

sys.modules["config"] = MagicMock()
spec = json.loads(sys.argv[1])
try:
    import autobot_shared
except BaseException as exc:
    sys.stdout.write(json.dumps({"autobot_shared": f"{type(exc).__name__}: {exc}"}) + "\\n")
    raise SystemExit(0)

def _is_test(name):
    leaf = name.rsplit(".", 1)[-1]
    return leaf.endswith("_test") or leaf.startswith("test_") or leaf == "conftest" or ".tests" in name

if spec["modules"]:
    targets = spec["modules"]
else:
    names = [m.name for m in pkgutil.walk_packages(autobot_shared.__path__, "autobot_shared.")]
    targets = sorted(n for n in names if not _is_test(n) and n not in set(spec["excluded"]))
failures = {}
for name in targets:
    try:
        importlib.import_module(name)
    except BaseException as exc:
        failures[name] = f"{type(exc).__name__}: {exc}"
sys.stdout.write(json.dumps({"targets": targets, "failures": failures}) + "\\n")
"""


def run_sweep(
    cwd: Path, modules: tuple[str, ...] = (), roots: tuple[Path, ...] = (), excluded: tuple[str, ...] = ()
) -> dict[str, object]:
    """Import *modules* (or, when empty, every non-test autobot_shared module) under a mocked config.

    Returns ``{"targets": [...], "failures": {module: error}}``. Fails outright when the interpreter
    crashes, when ``autobot_shared`` itself cannot import, or when a ``MagicMock/`` directory appears
    in *cwd* (a MagicMock's ``__fspath__`` yields one, and it must never become a log directory).
    """
    pythonpath = os.pathsep.join(str(p) for p in (*roots, REPO_ROOT))
    env = {**os.environ, "PYTHONPATH": pythonpath, "AUTOBOT_LOGS_DIR": str(cwd / "logs")}
    spec = json.dumps({"modules": list(modules), "excluded": sorted(excluded)})
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and inline script, no user input
        [sys.executable, "-c", _SWEEP, spec],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, f"sweep crashed:\n{result.stderr[-4000:]}"
    report: dict[str, object] = json.loads(result.stdout.strip().splitlines()[-1])
    assert "autobot_shared" not in report, f"the package itself failed to import: {report}"
    assert not (cwd / "MagicMock").exists()
    return report
