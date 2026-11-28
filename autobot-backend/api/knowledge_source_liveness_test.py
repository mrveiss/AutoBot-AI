# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The source-liveness sweep audits the admin's canonical id as the actor (#22338)."""

from unittest.mock import AsyncMock, patch

from api import knowledge_source_liveness
from testkit.canonical_gate import HUMAN_PRINCIPAL


async def test_the_sweep_audit_records_the_id_not_the_username():
    result = {"probed": 1, "outcomes": {}, "superseded": 0}
    with (
        patch.object(knowledge_source_liveness, "sweep_source_liveness", AsyncMock(return_value=result)),
        patch.object(knowledge_source_liveness, "audit_log", AsyncMock()) as audit,
    ):
        await knowledge_source_liveness.post_source_liveness_sweep(limit=5, admin=HUMAN_PRINCIPAL)
    assert audit.await_args.kwargs["user_id"] == "u-123"
