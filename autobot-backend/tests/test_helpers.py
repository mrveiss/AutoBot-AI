"""Shared helpers for backend e2e/integration tests."""

from autobot_shared.ssot_config import config


def get_test_backend_url() -> str:
    """Return backend base URL for e2e tests.

    Reads AUTOBOT_TEST_BACKEND_URL env var first so CI can override without code changes.
    Defaults to localhost:8001.
    """
    return config.test_backend_url
