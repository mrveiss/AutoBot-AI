# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A denied approval is audited with the caller's canonical id, never the mutable username (#22338)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api import approval_gates_approver
from testkit.canonical_gate import HUMAN_PRINCIPAL


async def test_a_denied_approval_audit_records_the_id():
    approval = SimpleNamespace(id="x", context={"action": "a"})
    user = {**HUMAN_PRINCIPAL, "role": "user"}
    with (
        patch.object(approval_gates_approver, "action_needs_elevated_approver", return_value=True),
        patch.object(approval_gates_approver, "audit_log", AsyncMock()) as audit,
        pytest.raises(HTTPException),
    ):
        await approval_gates_approver.require_action_approver_role(approval, user)
    assert audit.await_args.kwargs["user_id"] == "u-123"
