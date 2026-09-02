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


#: The integration package this guard lives in, anchored to the test file (#12993).
#:
#: This was ``Path("autobot-backend/integrations")`` -- a bare relative path,
#: resolved against the *process* working directory. Run from the repo root the
#: glob matched 23 modules; run from ``autobot-backend/`` it matched none, the
#: parametrised contract checks silently vanished, and the only surviving
#: signal was the emptiness guard below. The directory this file already lives
#: in is the directory to scan, by construction, so ask the file where it is.
_INTEGRATIONS_ROOT = Path(__file__).resolve().parent

#: Population floor. The tree carries 23 ``BaseIntegration`` subclasses today;
#: this is set well below that so ordinary additions and removals do not trip
#: it, while a collapsed sweep -- the #12993 failure mode -- still fails by
#: name instead of reading as a clean contract.
_MIN_SUBCLASSES = 12

#: Floor on the module count the glob itself reaches, checked separately from
#: the subclass count: a discovery that reads the right directory but stops
#: matching ``class X(BaseIntegration):`` is a different defect from one that
#: reads the wrong directory, and they must not share one error message.
_MIN_MODULES = 12


def _integration_modules():
    """Non-test Python modules in this package, anchored to this file."""
    return [py for py in sorted(_INTEGRATIONS_ROOT.glob("*.py")) if not py.name.endswith("_test.py")]


def _discover_subclasses():
    """Static-analysis discovery of BaseIntegration subclasses to avoid
    importing the heavy dep chain. Returns (file_path, class_name) tuples.
    """
    pat = re.compile(r"^class (\w+)\(BaseIntegration\):", re.M)
    out = []
    for py in _integration_modules():
        for cls_name in pat.findall(py.read_text(encoding="utf-8")):
            out.append((py, cls_name))
    return out


MODULES = _integration_modules()
SUBCLASSES = _discover_subclasses()


def _assert_population() -> None:
    """Raise unless the sweep reached the package it claims to scan.

    Called from the floor test *and* from the parametrised contract check, so
    the floor is evaluated before the substantive assertion whatever order the
    tests run in -- this suite runs under ``pytest-randomly``, so file order is
    not an ordering guarantee.
    """
    assert len(MODULES) >= _MIN_MODULES, (
        f"discovery reached only {len(MODULES)} modules under {_INTEGRATIONS_ROOT} "
        f"(floor {_MIN_MODULES}). FIX THE SWEEP -- the contract checks below are "
        "parametrised over this population and pass vacuously when it collapses."
    )


def test_the_sweep_reached_the_integration_package():
    """Population floor, evaluated before any contract assertion.

    A sweep that reaches nothing makes every check below vacuous, and a vacuous
    check reads exactly like a clean tree. This names the sweep as the thing to
    fix so the failure cannot be mistaken for a contract regression.
    """
    _assert_population()


def test_at_least_one_subclass_discovered():
    """Sanity: the discovery itself must work or every subsequent test
    becomes vacuous."""
    assert len(SUBCLASSES) >= _MIN_SUBCLASSES, (
        f"discovery returned {len(SUBCLASSES)} BaseIntegration subclasses across "
        f"{len(MODULES)} modules (floor {_MIN_SUBCLASSES}). FIX THE SWEEP -- do not "
        "lower this bound to make it pass."
    )


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
    _assert_population()
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
