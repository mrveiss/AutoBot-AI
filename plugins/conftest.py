# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Withdraw the ``plugins`` packages pytest installs for this tree's test modules (#18384).

``--import-mode=importlib`` (pytest.ini) registers every parent of a test module
in ``sys.modules``: ``plugins`` (a namespace package over the repository's
``plugins/`` directory), ``plugins.core-plugins`` and so on. pytest does it at
collection AND again when a module's first test is set up. The entries are not
stubs, so the ``sys.modules`` leak guard does not see them, but they outlive the
module and answer the plugin loader's ``name in sys.modules`` check for
``plugins`` / ``plugins.core_plugins`` in
``autobot_shared/plugin_sdk/loader_file_fallback_test.py``: an order-dependent
failure whenever both ran in one process.

They are therefore withdrawn twice: when collection finishes (the loader tests can
run before any plugin test) and when each plugin test module's last test is done.
Nothing in these tests resolves the parents afterwards (they load plugin code by
file path), and pytest re-registers them if the module is set up again.
"""

from __future__ import annotations

import sys

import pytest


def withdraw_plugins_packages() -> list[str]:
    """Remove ``plugins`` and every ``plugins.*`` entry; return the names removed."""
    names = [n for n in sys.modules if n == "plugins" or n.startswith("plugins.")]
    for name in names:
        sys.modules.pop(name, None)
    return names


@pytest.fixture(autouse=True, scope="module")
def _withdraw_plugins_packages_after_module():
    yield
    withdraw_plugins_packages()


def pytest_collection_finish(session) -> None:  # noqa: ARG001 - pytest hook signature
    withdraw_plugins_packages()
