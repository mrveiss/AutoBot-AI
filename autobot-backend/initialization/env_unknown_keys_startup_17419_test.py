# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Backend startup refuses unknown AUTOBOT_* keys on and after the deadline (#17419).

The deadline and "today" are injected from the constant, never typed as a date.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from repo_tests._paths import repo_root

import initialization.lifespan as lifespan
from autobot_shared import env_drift_detector as det
from autobot_shared import env_unknown_keys as unknown

_DEADLINE = unknown.UNKNOWN_KEY_REFUSE_AFTER
_TYPO = "AUTOBOT_NO_SUCH_KEY_17419"


def _inject(monkeypatch, *, today, keys) -> det.DriftReport:
    """Make the startup hook see a report built for *today* with *keys* unknown."""
    report = det.DriftReport(env_path="injected.env", unknown_keys=list(keys))
    report.unknown_suggestions = {key: None for key in keys}
    report.unknown_key_policy = unknown.resolve_policy(today)
    monkeypatch.setattr(det, "check_env_drift", lambda *_a, **_k: report)
    return report


async def test_before_the_deadline_an_unknown_key_warns_and_startup_continues(monkeypatch, caplog) -> None:
    report = _inject(monkeypatch, today=_DEADLINE - timedelta(days=1), keys=[_TYPO])

    with caplog.at_level(logging.WARNING):
        await lifespan._check_env_drift()  # must not raise

    assert report.unknown_key_policy == unknown.POLICY_WARN


@pytest.mark.parametrize("offset_days", [0, 30])
async def test_on_or_after_the_deadline_an_unknown_key_refuses_startup(monkeypatch, caplog, offset_days) -> None:
    report = _inject(monkeypatch, today=_DEADLINE + timedelta(days=offset_days), keys=[_TYPO])
    expected = unknown.describe_unknown_key(_TYPO, None, report.unknown_key_policy)

    with caplog.at_level(logging.ERROR), pytest.raises(unknown.UnknownEnvKeysRefused):
        await lifespan._check_env_drift()

    assert expected in caplog.text


async def test_on_or_after_the_deadline_with_no_unknown_keys_startup_continues(monkeypatch) -> None:
    _inject(monkeypatch, today=_DEADLINE, keys=[])

    await lifespan._check_env_drift()  # must not raise


def test_the_docs_state_the_refuse_date_read_from_the_constant() -> None:
    docs = (repo_root() / "docs" / "developer" / "ENV_VARS.md").read_text(encoding="utf-8")

    assert unknown.refuse_notice() in docs
    assert _DEADLINE.isoformat() in unknown.refuse_notice()
