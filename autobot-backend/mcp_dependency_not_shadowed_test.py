# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``import mcp`` must resolve to the installed SDK, never a repo package (#16449).

``autobot-backend/mcp/`` used to shadow the real ``mcp`` PyPI package
(``requirements.txt``'s ``mcp>=2.1.1``) for every module with
``autobot-backend/`` on ``sys.path`` — every ``from mcp.X import Y`` anywhere
in the tree resolved to that local package's own submodules
(``mcp.autobot_server``, ``mcp.auth_throttle``), and the installed SDK was
unreachable by its own name. Renamed to ``mcp_server`` to free the name; this
is the regression guard.
"""

from __future__ import annotations

import importlib
import sys


def test_import_mcp_resolves_to_the_installed_sdk_not_a_repo_package() -> None:
    sys.modules.pop("mcp", None)
    mcp = importlib.import_module("mcp")
    path = getattr(mcp, "__file__", "") or ""
    assert "site-packages" in path or "dist-packages" in path, (
        f"import mcp resolved to {path!r}, not an installed package — a repo-local "
        "package is shadowing the mcp PyPI SDK again"
    )
    assert "/autobot-backend/" not in path.replace("\\", "/"), (
        f"import mcp resolved to {path!r}, inside autobot-backend/ -- a local " "package is shadowing the mcp PyPI SDK"
    )


def test_the_renamed_package_is_importable_under_its_new_name() -> None:
    mcp_server = importlib.import_module("mcp_server")
    assert "autobot-backend" in (getattr(mcp_server, "__file__", "") or "")
