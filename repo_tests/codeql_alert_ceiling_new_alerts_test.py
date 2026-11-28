# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The CodeQL gate compares a dispatched run's alerts with the default branch's (#20825).

A pull request used to be analysed under `refs/pull/<n>/merge`, where GitHub compared it with its base. A
dispatched run is analysed under `refs/heads/<branch>`, so check_codeql_alert_ceiling.sh makes the comparison
itself. Driven with the fake `gh` of codeql_alert_ceiling_is_wired_15333_test.py, which answers the default
branch's alerts apart from the head ref's.
"""

from __future__ import annotations

from repo_tests.codeql_alert_ceiling_is_wired_15333_test import (
    _CHECKS_WITHOUT_CODEQL,
    _CODEQL_AT_SHA,
    _gate,
)

_ONE = '[{"number":7}]'
_TWO = '[{"number":7},{"number":9}]'


def test_an_alert_open_on_the_head_and_not_on_the_default_branch_fails(tmp_path):
    """SHOULD trip: alert 9 is new, even though the absolute count would sit at the ceiling."""
    result = _gate(tmp_path, analyses=_CODEQL_AT_SHA, alerts=_TWO, alerts_main=_ONE)
    assert result.returncode == 1
    assert "not on refs/heads/main: 9" in result.stderr


def test_no_new_alert_passes_the_comparison_and_the_gate(tmp_path):
    """SHOULD NOT trip: nothing open on either ref (the ceiling is 0)."""
    result = _gate(tmp_path, analyses=_CODEQL_AT_SHA, alerts="[]", alerts_main="[]")
    assert result.returncode == 0, result.stderr
    assert "no alert on refs/pull/1/merge is new against refs/heads/main" in result.stdout


def test_a_head_that_fixed_an_alert_is_not_new(tmp_path):
    result = _gate(tmp_path, analyses=_CODEQL_AT_SHA, alerts="[]", alerts_main=_ONE)
    assert result.returncode == 0, result.stderr
    assert "is new against" in result.stdout


def test_an_errored_default_branch_read_fails_closed(tmp_path):
    result = _gate(tmp_path, analyses=_CODEQL_AT_SHA, alerts=_ONE, alerts_main="not json")
    assert result.returncode == 1
    assert "refs/heads/main" in result.stderr


def test_a_docs_only_change_skips_the_comparison_and_neither_hangs_nor_fails(tmp_path):
    """CodeQL never ran (no analysis, no check): the default-branch count stands, with no comparison and no wait."""
    result = _gate(tmp_path, analyses="[]", alerts="[]", alerts_unscoped="[]", alerts_main=_ONE, checks=_CHECKS_WITHOUT_CODEQL, wait_s=0)
    assert result.returncode == 0, result.stderr
    assert "is new against" not in result.stdout
    assert "CodeQL did not run for this ref" in result.stdout
