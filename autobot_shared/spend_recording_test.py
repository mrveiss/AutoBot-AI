# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The spend-recording hook: delivers, warns once per site when unset, never loses the answer (#19650)."""

import logging

import pytest

from autobot_shared import spend_recording as hook


@pytest.fixture(autouse=True)
def _clean_hook():
    hook._reset_for_tests()
    yield
    hook._reset_for_tests()


@pytest.mark.asyncio
async def test_a_registered_recorder_receives_the_response_site_and_metadata():
    seen = []

    async def recorder(response, *, endpoint, metadata):
        seen.append((response, endpoint, metadata))

    hook.register_spend_recorder(recorder)
    await hook.report_spend("resp", site="site_a", metadata={"k": 1})

    assert seen == [("resp", "site_a", {"k": 1})]


@pytest.mark.asyncio
async def test_no_recorder_warns_once_per_site_and_does_not_raise(caplog):
    with caplog.at_level(logging.WARNING, logger=hook.logger.name):
        await hook.report_spend("r", site="site_a")
        await hook.report_spend("r", site="site_a")
        await hook.report_spend("r", site="site_b")

    warned = [r.getMessage() for r in caplog.records if "no spend recorder" in r.getMessage()]
    assert len(warned) == 2
    assert "site_a" in warned[0] and "site_b" in warned[1]


@pytest.mark.asyncio
async def test_a_failing_recorder_is_logged_and_does_not_raise(caplog):
    async def broken(response, *, endpoint, metadata):
        raise RuntimeError("tracker down")

    hook.register_spend_recorder(broken)
    with caplog.at_level(logging.ERROR, logger=hook.logger.name):
        await hook.report_spend("r", site="site_a")

    failures = [r for r in caplog.records if "Spend recorder failed" in r.getMessage()]
    assert len(failures) == 1 and failures[0].exc_info is not None


@pytest.mark.asyncio
async def test_registration_toggles_the_registered_flag():
    assert hook.spend_recorder_registered() is False

    async def recorder(response, *, endpoint, metadata):
        return None

    hook.register_spend_recorder(recorder)
    assert hook.spend_recorder_registered() is True
