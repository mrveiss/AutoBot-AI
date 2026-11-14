# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chat-session lease holder is the shared host-and-process identity plus operation and suffix (#21518)."""

import re
from unittest.mock import patch

import pytest

from chat_history import session_lease as lease_mod


@pytest.mark.parametrize(
    ("identity", "operation"),
    [("backend-2-4242", "save_session"), ("node-9-7", "rename_session")],
    ids=["save", "rename"],
)
async def test_the_holder_is_identity_operation_and_a_random_suffix(identity: str, operation: str) -> None:
    with patch.object(lease_mod, "worker_identity", return_value=identity):
        holder = lease_mod.SessionLease("s1", operation)._lease.worker_id
    assert re.fullmatch(re.escape(f"{identity}:{operation}:") + r"[0-9a-f]{8}", holder)
