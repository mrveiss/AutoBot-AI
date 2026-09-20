# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Importing credential_store must not import any concrete connector (#17138).

``knowledge/connectors/__init__.py`` used to import every connector module
(gdrive, nextcloud, gitlab, ...) at package-import time, so anything that
touched a SIBLING module in this package -- ``credential_store.py``, which
has no connector dependency of its own -- paid for all of them anyway, since
Python always runs a package's ``__init__`` before any of its submodules.
Discovered as a recurring red on unrelated PRs (#16444: aiohttp via
gdrive.py; #17134: defusedxml via nextcloud.py), because each connector's
own third-party dependency landed on the migration-gate job's deliberately
minimal pip list.

Run as a subprocess, not in-process: this test suite (and pytest collection
generally) has almost certainly already imported half the connectors package
by the time any test function runs, so ``sys.modules`` in-process proves
nothing about a fresh import.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).parents[2]
_WORKTREE_ROOT = _BACKEND_DIR.parent

# Every concrete connector's real module -- if package import stays lazy,
# none of these may appear in sys.modules after importing credential_store.
_CONCRETE_CONNECTOR_MODULES = (
    "knowledge.connectors.database",
    "knowledge.connectors.external_adapter",
    "knowledge.connectors.file_server",
    "knowledge.connectors.gdrive",
    "knowledge.connectors.gitlab",
    "knowledge.connectors.nextcloud",
    "knowledge.connectors.notion",
    "knowledge.connectors.onedrive",
    "knowledge.connectors.web_crawler",
    "knowledge.connectors.confluence",
    "knowledge.connectors.jira",
    "knowledge.connectors.slack",
    "knowledge.connectors.mock",
    "knowledge.connectors.oauth_flow",
)


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_BACKEND_DIR),
        capture_output=True,
        text=True,
        env={"PYTHONPATH": f"{_WORKTREE_ROOT}{__import__('os').pathsep}{_BACKEND_DIR}"},
        timeout=60,
    )


def test_importing_credential_store_pulls_in_no_concrete_connector() -> None:
    script = (
        "import sys; "
        "from knowledge.connectors.credential_store import ConnectorCredentialStore, get_credential_store; "
        f"leaked = sorted(m for m in {_CONCRETE_CONNECTOR_MODULES!r} if m in sys.modules); "
        "print('LEAKED:' + ','.join(leaked) if leaked else 'CLEAN')"
    )
    result = _run(script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CLEAN" in result.stdout, result.stdout + result.stderr


def test_importing_the_connectors_package_itself_pulls_in_no_concrete_connector() -> None:
    """The package's own docstring/`__all__` must stay importable without the
    eager side effect it used to have -- `import knowledge.connectors` alone,
    no submodule, no registry call."""
    script = (
        "import sys; "
        "import knowledge.connectors; "
        f"leaked = sorted(m for m in {_CONCRETE_CONNECTOR_MODULES!r} if m in sys.modules); "
        "print('LEAKED:' + ','.join(leaked) if leaked else 'CLEAN')"
    )
    result = _run(script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CLEAN" in result.stdout, result.stdout + result.stderr


def test_create_still_resolves_a_real_connector_on_first_use() -> None:
    """The lazy path must still actually work: create() for a real,
    unconditional type imports exactly that module and returns a real
    connector instance -- proves the registry didn't just start returning
    "unknown type" for everything."""
    script = (
        "import asyncio, sys; "
        "from knowledge.connectors.registry import ConnectorRegistry; "
        "from knowledge.connectors.models import ConnectorConfig; "
        "cfg = ConnectorConfig(connector_id='t', connector_type='file_server', name='t', "
        "config={'base_path': '/tmp', 'include_patterns': ['*'], 'exclude_patterns': []}); "
        "instance = asyncio.run(ConnectorRegistry.create(cfg)); "
        "assert 'knowledge.connectors.file_server' in sys.modules; "
        "assert type(instance).__name__ == 'FileServerConnector', type(instance).__name__; "
        "print('OK')"
    )
    result = _run(script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout, result.stdout + result.stderr
