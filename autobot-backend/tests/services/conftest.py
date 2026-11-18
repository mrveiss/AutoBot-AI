# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fixtures for the services tests."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def kb_reader():
    """The user a grounding reads the KB as; every fake KB fact is visible to them.

    #16665 fails closed on no user, so a test that expects KB facts to count grounds
    as someone. The patched filter checks the read carries this user.
    """
    reader = "alice"

    async def visible(results, _kb, user_id):
        assert user_id == reader
        return results

    with patch("services.grounded_agent.filter_for_user_id", new=AsyncMock(side_effect=visible)):
        yield reader
