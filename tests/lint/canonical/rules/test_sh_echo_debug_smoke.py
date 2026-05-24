"""Tests for the sh-echo-debug-smoke rule (Wave 0 infra smoke-test rule)."""

from pathlib import Path

import pytest

from tools.lint.canonical.infra_rules import sh_echo_debug_smoke

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sh_echo_debug_smoke"


def test_positive_fixture_produces_one_diagnostic():
    diags = sh_echo_debug_smoke.check(FIXTURES / "positive.sh")
    assert len(diags) == 1
    assert diags[0].rule_id == "sh-echo-debug-smoke"


def test_negative_fixture_produces_no_diagnostics():
    diags = sh_echo_debug_smoke.check(FIXTURES / "negative.sh")
    assert diags == []


def test_rule_metadata_present():
    for attr in ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT"):
        assert hasattr(sh_echo_debug_smoke, attr)
