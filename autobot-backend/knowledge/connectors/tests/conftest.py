# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fixtures for the connector credential tests."""

from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def _pinned_connector_stub(monkeypatch):
    """No DNS in unit tests: a refresh pins its token URL to a public IP (#22234).

    The pin and the create-time public-HTTPS check are exercised for real in
    ``api/secrets_connector_bridge_16428_test.py``.
    """
    from knowledge.connectors import oauth_bundle

    monkeypatch.setattr(oauth_bundle, "pinned_connector", AsyncMock(return_value=None))
