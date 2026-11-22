# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Unknown ``AUTOBOT_*`` keys: nearest-match suggestion, announced refuse deadline, one policy switch (#17419)."""

from __future__ import annotations

from datetime import date, timedelta

from autobot_shared import env_drift_detector as det
from autobot_shared import env_unknown_keys as unknown

DECLARED = {"AUTOBOT_REDIS_HOST", "AUTOBOT_BACKEND_PORT", "AUTOBOT_SSH_USER"}
#: Enough names that the detector is not asserting against its own fixtures.
MIN_DECLARED_NAMES = 300


def test_a_typo_gets_its_nearest_declared_name_and_a_stranger_gets_none() -> None:
    assert unknown.suggest_key("AUTOBOT_REDIS_HOSTT", DECLARED) == "AUTOBOT_REDIS_HOST"
    assert unknown.suggest_key("AUTOBOT_COMPLETELY_UNRELATED_THING", DECLARED) is None


def test_the_policy_is_warn_before_the_deadline_and_refuse_on_and_after_it() -> None:
    deadline = unknown.UNKNOWN_KEY_REFUSE_AFTER
    assert unknown.resolve_policy(deadline - timedelta(days=1)) == unknown.POLICY_WARN
    assert unknown.resolve_policy(deadline) == unknown.POLICY_REFUSE
    assert unknown.resolve_policy(deadline + timedelta(days=1)) == unknown.POLICY_REFUSE


def test_the_message_reads_the_deadline_it_is_given_and_never_a_typed_date() -> None:
    other = date(2031, 7, 9)
    warn = unknown.describe_unknown_key("AUTOBOT_X", None, unknown.POLICY_WARN, deadline=other)
    refuse = unknown.describe_unknown_key("AUTOBOT_X", "AUTOBOT_Y", unknown.POLICY_REFUSE, deadline=other)
    assert "will be refused from 2031-07-09" in warn
    assert "refused since 2031-07-09" in refuse and "did you mean 'AUTOBOT_Y'?" in refuse
    default = unknown.describe_unknown_key("AUTOBOT_X", None, unknown.POLICY_WARN)
    assert unknown.UNKNOWN_KEY_REFUSE_AFTER.isoformat() in default


def test_the_detector_reports_only_undeclared_autobot_keys() -> None:
    env = {"AUTOBOT_REDIS_HOST": "x", "AUTOBOT_REDIS_HOSTT": "x", "VITE_FOO": "1"}
    assert det._find_unknown_keys(DECLARED, env) == ["AUTOBOT_REDIS_HOSTT"]


def test_refused_needs_both_an_unknown_key_and_the_refuse_policy() -> None:
    warn = det.DriftReport(env_path="x", unknown_keys=["AUTOBOT_A"])
    refuse = det.DriftReport(env_path="x", unknown_keys=["AUTOBOT_A"], unknown_key_policy=unknown.POLICY_REFUSE)
    clean = det.DriftReport(env_path="x", unknown_key_policy=unknown.POLICY_REFUSE)
    assert (warn.refused, refuse.refused, clean.refused) == (False, True, False)


def test_declared_names_cover_the_models_and_the_registry() -> None:
    names = unknown.declared_env_names()
    assert len(names) >= MIN_DECLARED_NAMES, f"only {len(names)} names declared"
    assert {"AUTOBOT_SSH_KEY", "AUTOBOT_SSH_USER"} <= names


def test_a_mistyped_key_in_an_env_file_is_reported_with_its_suggestion(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AUTOBOT_SSH_USERR=ops\n", encoding="utf-8")
    report = det.check_env_drift(str(env_file))
    assert report.unknown_keys == ["AUTOBOT_SSH_USERR"]
    assert report.unknown_suggestions == {"AUTOBOT_SSH_USERR": "AUTOBOT_SSH_USER"}


def test_a_per_agent_provider_override_is_supported_and_a_misspelt_suffix_is_not() -> None:
    assert unknown.is_agent_provider_override("AUTOBOT_CODE_ANALYSIS_PROVIDER")
    assert unknown.is_agent_provider_override("AUTOBOT_RESEARCH_PROVIDER")
    assert not unknown.is_agent_provider_override("AUTOBOT_CODE_ANALYSIS_PROVIDR")
    assert not unknown.is_agent_provider_override("AUTOBOT_PROVIDER")
    env = {"AUTOBOT_RESEARCH_PROVIDER": "openai", "AUTOBOT_RESEARCH_PROVIDR": "openai"}
    assert det._find_unknown_keys(DECLARED, env) == ["AUTOBOT_RESEARCH_PROVIDR"]
