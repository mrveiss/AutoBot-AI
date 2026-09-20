# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``jsonschema`` must not import merely from loading the plugin SDK (#17138).

``loader.py`` used to bind ``jsonschema.Draft202012Validator`` at module
level, so anything reaching ``middleware/__init__.py -> plugin_sdk/__init__.py
-> loader.py`` paid for ``jsonschema`` whether or not it ever loaded or
validated a plugin -- reached from ``api/secrets.py``'s own import graph and
landed as a red on the migration-gate job's deliberately minimal pip list.

Run as a subprocess: this test suite has almost certainly already imported
``jsonschema`` by the time any in-process test runs, so ``sys.modules``
in-process proves nothing about a fresh import.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]


def _run(script: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": f"{_REPO_ROOT}{os.pathsep}{_REPO_ROOT / 'autobot-backend'}"}
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_importing_plugin_sdk_pulls_in_no_jsonschema() -> None:
    script = "import sys; import autobot_shared.plugin_sdk; print('LEAKED' if 'jsonschema' in sys.modules else 'CLEAN')"
    result = _run(script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CLEAN" in result.stdout, result.stdout + result.stderr


def test_importing_loader_module_pulls_in_no_jsonschema() -> None:
    script = (
        "import sys; import autobot_shared.plugin_sdk.loader; "
        "print('LEAKED' if 'jsonschema' in sys.modules else 'CLEAN')"
    )
    result = _run(script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CLEAN" in result.stdout, result.stdout + result.stderr


def test_schema_validation_still_actually_works_on_first_use() -> None:
    """The lazy path must still work: calling the validators imports
    jsonschema and produces real results, not a silently-broken no-op."""
    script = (
        "import sys\n"
        "from autobot_shared.plugin_sdk.loader import _validate_config_schema, _validate_config_against_schema\n"
        "from autobot_shared.plugin_sdk.base import PluginLoadError\n"
        "_validate_config_schema('p', {'type': 'object', 'properties': {'x': {'type': 'string'}}})\n"
        "assert 'jsonschema' in sys.modules\n"
        "try:\n"
        "    _validate_config_schema('p', {'type': 'not-a-real-type'})\n"
        "    raise SystemExit('expected PluginLoadError for an invalid schema')\n"
        "except PluginLoadError:\n"
        "    pass\n"
        "try:\n"
        "    _validate_config_against_schema('p', {'x': 5}, {'type': 'object', 'properties': {'x': {'type': 'string'}}})\n"
        "    raise SystemExit('expected PluginLoadError for a non-conforming config')\n"
        "except PluginLoadError:\n"
        "    pass\n"
        "print('OK')\n"
    )
    result = _run(script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout, result.stdout + result.stderr
