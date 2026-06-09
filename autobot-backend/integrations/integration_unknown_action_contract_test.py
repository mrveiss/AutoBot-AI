# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Contract test for BaseIntegration.execute_action's unknown-action behaviour
(Issue #6658).

The base contract (integrations/base.py:107-112) declares execute_action as
``async def -> Dict[str, Any]`` with no documented Raises clause. Every
concrete subclass must therefore return an error dict — not raise
ValueError — when handed an action it doesn't know about. This test
parametrically verifies the contract across the whole integration tree so
the next person to add an integration can't silently re-introduce the
violation.
"""

import re
from pathlib import Path

import pytest


def _discover_subclasses():
    """Static-analysis discovery of BaseIntegration subclasses to avoid
    importing the heavy dep chain. Returns (file_path, class_name) tuples.
    """
    pat = re.compile(r"^class (\w+)\(BaseIntegration\):", re.M)
    root = Path("autobot-backend/integrations")
    out = []
    for py in sorted(root.glob("*.py")):
        if py.name.endswith("_test.py"):
            continue
        for cls_name in pat.findall(py.read_text(encoding="utf-8")):
            out.append((py, cls_name))
    return out


SUBCLASSES = _discover_subclasses()


def test_at_least_one_subclass_discovered():
    """Sanity: the discovery itself must work or every subsequent test
    becomes vacuous."""
    assert SUBCLASSES, "discovery returned zero BaseIntegration subclasses"


@pytest.mark.parametrize(
    "src_file,class_name",
    SUBCLASSES,
    ids=[f"{p.stem}::{n}" for p, n in SUBCLASSES],
)
def test_no_subclass_raises_value_error_on_unknown_action(src_file, class_name):
    """Static check: no BaseIntegration subclass body contains a
    ``raise ValueError(f"(Unknown|Unsupported) action: {action}")`` line.

    This is the contract enforced by #6658 — the base type signature
    promises Dict[str, Any], so unknown actions must surface as
    {"error": ...} (matching JiraIntegration / TrelloIntegration /
    AsanaIntegration / NotionIntegration which already did).
    """
    text = src_file.read_text(encoding="utf-8")
    forbidden = re.compile(r'raise ValueError\(f"(Unknown|Unsupported) action: \{action\}"\)')
    matches = forbidden.findall(text)
    assert not matches, (
        f"{src_file.name} still raises ValueError on unknown action " f"(violates BaseIntegration contract — see #6658)"
    )


# Live behavioural check for one canonical violator from the issue
@pytest.mark.asyncio
async def test_github_integration_returns_error_dict_for_unknown_action():
    """Live test: GitHubIntegration was one of six canonical violators
    in #6658. The fix must produce a dict {"error": ...} for unknown actions.
    """
    try:
        from integrations.base import IntegrationConfig
        from integrations.github_integration import GitHubIntegration
    except Exception as exc:  # pragma: no cover — env-dependent
        pytest.skip(f"GitHub dep chain unavailable: {exc}")

    cfg = IntegrationConfig(
        name="test-gh",
        provider="github",
        api_key="x",
        base_url="https://api.github.com",
    )
    gh = GitHubIntegration(cfg)
    result = await gh.execute_action("__never_a_real_action__", {})
    assert isinstance(result, dict), "expected Dict per BaseIntegration contract"
    assert "error" in result, f"expected error key, got {result!r}"
    assert "Unknown action" in result["error"]
