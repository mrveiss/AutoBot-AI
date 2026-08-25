# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SDK's query defaults must not drift from the platform's (#15053).

``libs/autobot-sdk-python`` ships to PyPI depending on ``httpx`` and
``pydantic`` alone, so it cannot import ``autobot_shared.ssot_constants`` --
that would pull the backend into a client install. Its pagination and search
defaults are therefore duplicated by hand from ``QueryDefaults``.

Duplication without a pin is how a client and a server come to disagree about a
page size while each looks correct on its own: nothing fails, the SDK simply
returns 50 rows where the server changed to 25. This guard fails instead.

It reads the SDK constants with ``ast`` rather than importing them, because
``libs/autobot-sdk-python`` is not on ``sys.path`` for the repo test run and a
sys.path insertion here would be a second, quieter way for the two trees to
couple.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from autobot_shared.ssot_constants import QueryDefaults

SDK_DEFAULTS = Path("libs/autobot-sdk-python/autobot_sdk/defaults.py")


def project_root() -> Path:
    """Repository root via git, or a skip when this is not a git checkout."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return Path(out.stdout.strip())


def sdk_constants() -> dict[str, int]:
    """Every module-level ``NAME: int = <literal>`` in the SDK defaults module."""
    path = project_root() / SDK_DEFAULTS
    assert path.is_file(), f"{SDK_DEFAULTS} is missing -- the SDK defaults moved without updating this guard"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                found[node.target.id] = node.value.value
    return found


def test_the_guard_can_see_the_sdk_constants():
    """Fail loudly if the AST walk stops matching -- an empty read must not pass silently."""
    found = sdk_constants()
    assert found, f"parsed no int constants out of {SDK_DEFAULTS}; the guard below would be vacuous"
    assert "DEFAULT_SEARCH_LIMIT" in found, f"expected DEFAULT_SEARCH_LIMIT among {sorted(found)}"


def test_every_sdk_default_matches_the_platform_value():
    for name, sdk_value in sdk_constants().items():
        platform_value = getattr(QueryDefaults, name, None)
        assert platform_value is not None, (
            f"{name} exists in the SDK but not in QueryDefaults. "
            "An SDK default with no platform counterpart cannot be kept honest -- "
            "either add it to QueryDefaults or give it a name that is not claiming to mirror one."
        )
        assert sdk_value == platform_value, (
            f"{name}: SDK says {sdk_value}, QueryDefaults says {platform_value}. "
            "Change both or neither -- a client and a server that disagree about this "
            "produce wrong-sized pages with no error on either side."
        )
