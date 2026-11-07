# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for backend e2e/integration tests."""

import pytest

from autobot_shared.live_service_probe import require_live_endpoint
from autobot_shared.ssot_config import config


def get_test_backend_url() -> str:
    """Return backend base URL for e2e tests.

    Reads AUTOBOT_TEST_BACKEND_URL env var first so CI can override without code changes.
    Defaults to localhost:8001.
    """
    return config.test_backend_url


def live_backend_url() -> str:
    """The backend URL for a test that dials it, or a skip (#19479).

    The configured URL defaults to the local backend, which on a machine that also runs an
    install is the user's live system. A dialing test runs only when the run opted in
    (``AUTOBOT_LIVE_TESTS=1``) and something listens there.
    """
    url = get_test_backend_url()
    if not url:  # CI's python-suite sets no AUTOBOT_TEST_BACKEND_URL (#14920)
        pytest.skip("no backend URL configured (AUTOBOT_TEST_BACKEND_URL) -- this test drives a live backend")
    require_live_endpoint(url, what="the AutoBot backend under test")
    return url
