# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""SLM-configurable findings policy read + safe defaults (#11271)."""

from unittest.mock import AsyncMock, patch

import pytest

from llc.services.findings_policy import FindingsPolicy, get_findings_policy


@pytest.mark.asyncio
async def test_defaults_when_no_slm_client():
    with patch("llc.services.findings_policy.get_slm_client", return_value=None):
        policy = await get_findings_policy()
    assert policy == FindingsPolicy(
        enabled=False,
        min_severity="medium",
        require_approval_to_promote=False,
        run_on_index=False,
        verify_batch_size=10,
    )
    assert policy.enabled is False


@pytest.mark.asyncio
async def test_parses_policy_from_slm():
    with patch(
        "llc.services.findings_policy._fetch_policy_json",
        AsyncMock(
            return_value={
                "enabled": True,
                "min_severity": "high",
                "require_approval_to_promote": True,
                "run_on_index": True,
                "verify_batch_size": 5,
            }
        ),
    ):
        policy = await get_findings_policy()
    assert policy.enabled is True
    assert policy.min_severity == "high"
    assert policy.require_approval_to_promote is True
    assert policy.run_on_index is True
    assert policy.verify_batch_size == 5


@pytest.mark.asyncio
async def test_defaults_on_malformed():
    with patch("llc.services.findings_policy._fetch_policy_json", AsyncMock(return_value={"bad": "x"})):
        policy = await get_findings_policy()
    assert policy == FindingsPolicy(
        enabled=False,
        min_severity="medium",
        require_approval_to_promote=False,
        run_on_index=False,
        verify_batch_size=10,
    )
