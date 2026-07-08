# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""SLM-configurable disposal policy read + safe defaults (#11129 P2)."""

from unittest.mock import AsyncMock, patch

import pytest

from llc.services.disposal_policy import DisposalPolicy, get_disposal_policy


@pytest.mark.asyncio
async def test_defaults_when_no_slm_client():
    with patch("llc.services.disposal_policy.get_slm_client", return_value=None):
        policy = await get_disposal_policy()
    assert policy == DisposalPolicy(retention_days=0, require_approval=False)


@pytest.mark.asyncio
async def test_parses_policy_from_slm():
    with patch(
        "llc.services.disposal_policy._fetch_policy_json",
        AsyncMock(return_value={"retention_days": 30, "require_approval": True}),
    ):
        policy = await get_disposal_policy()
    assert policy.retention_days == 30
    assert policy.require_approval is True


@pytest.mark.asyncio
async def test_defaults_on_malformed():
    with patch("llc.services.disposal_policy._fetch_policy_json", AsyncMock(return_value={"bad": "x"})):
        policy = await get_disposal_policy()
    assert policy == DisposalPolicy(retention_days=0, require_approval=False)
