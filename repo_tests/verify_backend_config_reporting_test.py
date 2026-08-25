# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A verifier must not report success for a check that never ran (#14870).

``verify_backend_config.py`` has three checks. Two read the workflow registry
statically and always pass; only ``route registration`` mounts the router and
asserts the execute endpoint exists — the single claim the script's success
message actually makes.

Its ``summary()`` used to return 0 whenever nothing failed, so when backend
imports were unavailable the essential check was skipped and the script still
printed ``✅ Workflow router registration verified``. A verifier that certifies
what it could not look at is worse than no verifier: the green tick is taken as
evidence, and the thing it names goes unchecked.

These tests pin the three outcomes apart. ``test_a_skipped_essential_check_is_not_success``
is the one that fails if the fix is reverted.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "utilities" / "verify_backend_config.py"


def _load_by_path(path: pathlib.Path, module_name: str):
    """Import a standalone script by path -- its directory is not a package.

    Install and restore in the same ``try/finally``: leaving the key behind
    trips the session-finish leak guard (#13361, #15076), which fails the run
    after every test has passed.
    """
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous


@pytest.fixture(scope="module")
def verifier():
    assert _SCRIPT.is_file(), f"{_SCRIPT.relative_to(_REPO_ROOT)} moved -- this guard is looking at nothing"
    return _load_by_path(_SCRIPT, "verify_backend_config_under_test")


def test_the_essential_check_name_matches_a_real_call_site(verifier):
    """Non-vacuity: the constant must name a check the script actually records.

    If ``ESSENTIAL_CHECK`` drifted from the name passed to ``record_skip``, every
    assertion below would still pass while guarding nothing.
    """
    source = _SCRIPT.read_text(encoding="utf-8")
    assert (
        f'name = "{verifier.ESSENTIAL_CHECK}"' in source
    ), f"ESSENTIAL_CHECK is {verifier.ESSENTIAL_CHECK!r} but no check declares that name"


def test_a_clean_run_reports_success(verifier):
    results = verifier.CheckResults()
    results.record_pass("registry entry", "found")
    results.record_pass(verifier.ESSENTIAL_CHECK, "endpoint registered")
    assert results.summary() == 0


def test_a_skipped_essential_check_is_not_success(verifier):
    """The regression this guard exists for: static checks passing is not verification."""
    results = verifier.CheckResults()
    results.record_pass("registry entry", "found")
    results.record_pass("router module", "resolves")
    results.record_skip(verifier.ESSENTIAL_CHECK, "backend imports unavailable")
    assert results.summary() == 1, (
        "the only check that exercises route registration was skipped, "
        "so the run must not exit 0 -- the other two only read the registry as text"
    )


def test_a_skipped_non_essential_check_still_succeeds(verifier):
    """The counterweight: not every skip is fatal, or the rule would be 'any skip fails'."""
    results = verifier.CheckResults()
    results.record_pass(verifier.ESSENTIAL_CHECK, "endpoint registered")
    results.record_skip("router module", "registry entry unavailable")
    assert results.summary() == 0


def test_a_failure_still_fails(verifier):
    results = verifier.CheckResults()
    results.record_pass(verifier.ESSENTIAL_CHECK, "endpoint registered")
    results.record_fail("registry entry", "missing")
    assert results.summary() == 1


def test_no_checks_at_all_is_not_success(verifier):
    """An empty run has verified nothing, whatever the counters say."""
    assert verifier.CheckResults().summary() == 1
