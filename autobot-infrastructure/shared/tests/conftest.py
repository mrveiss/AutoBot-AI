# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Test Suite Configuration
Provides pytest fixtures with configuration-driven test setup.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# `autobot-user-backend/` was renamed to `autobot-backend/` wholesale by
# 00ae80e10c (role-based repo restructuring, #926) — every path under it moved
# R100 — but this shim kept pointing at the old name, so it added a directory
# that does not exist and supplied nothing (#15161).
#
# What that cost depended entirely on how pytest was invoked, which is why it
# survived so long:
#
#   * `pytest autobot-infrastructure/shared/tests` — rootdir is THIS directory,
#     so the repo-root pytest.ini is not read, nothing puts `config` on the path,
#     and the import below aborted collection of the whole tree with
#     `ImportError: cannot import name 'unified_config_manager' from 'config'`.
#   * `pytest autobot-infrastructure/shared/tests libs` — what marker-tests.yml
#     runs. rootdir is the repository root, whose pytest.ini carries
#     `pythonpath = . autobot-backend ...`, so `config` resolved anyway and the
#     shim's failure was invisible.
#
# Repointing it makes this tree collect on its own terms instead of borrowing a
# path entry from whichever rootdir the caller happened to select. Appended, not
# inserted at position 0, so it cannot shadow a repo-root package for the other
# roots sharing the same pytest session: `autobot-backend/config` is a regular
# package and the repository root's `config/` is a namespace package, so the
# regular one wins regardless of order.
project_root = Path(__file__).parent.parent.parent.parent
_backend_path = str(project_root / "autobot-backend")
if _backend_path not in sys.path:
    sys.path.append(_backend_path)

# Canonical config manager: autobot-backend/config/__init__.py resolves the
# `unified_config_manager` attribute lazily onto config.manager.ConfigManager.
from config import unified_config_manager


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def config() -> Dict[str, Any]:
    """
    Provide unified configuration for all tests.
    No hardcoded values - everything from config.
    """
    return {
        "backend": unified_config_manager.get_backend_config(),
        "redis": unified_config_manager.get_redis_config(),
        "services": unified_config_manager.get_distributed_services_config(),
        # ConfigManager exposes no get_chroma_config(); the chroma settings are
        # a config section like `system` below.
        "chroma": unified_config_manager.get_config_section("chroma") or {},
        "system": unified_config_manager.get_config_section("system") or {},
    }


@pytest.fixture(scope="session")
def backend_url(config) -> str:
    """Get backend API URL from configuration."""
    backend_config = config["backend"]
    host = backend_config.get("host", "localhost")
    port = backend_config.get("port", 8001)
    return f"http://{host}:{port}"


@pytest.fixture(scope="session")
def redis_url(config) -> str:
    """Get Redis URL from configuration."""
    redis_config = config["redis"]
    host = redis_config.get("host", "localhost")
    port = redis_config.get("port", 6379)
    db = redis_config.get("db", 0)
    return f"redis://{host}:{port}/{db}"


@pytest.fixture(scope="session")
def frontend_url(config) -> str:
    """Get frontend URL from configuration."""
    services = config["services"]
    frontend_config = services.get("frontend", {})
    host = frontend_config.get("host", "localhost")
    port = frontend_config.get("port", 5173)
    return f"http://{host}:{port}"


@pytest.fixture
def test_data_dir() -> Path:
    """Get test data directory."""
    return Path(__file__).parent / "fixtures" / "data"


@pytest.fixture
def temp_dir(tmp_path) -> Path:
    """Provide temporary directory for test files."""
    return tmp_path


@pytest.fixture(autouse=True)
def set_test_environment():
    """
    Automatically set TEST environment variables for all tests.
    Prevents tests from affecting production data.
    """
    original_env = dict(os.environ)

    # Set test environment markers
    os.environ["AUTOBOT_TEST_MODE"] = "true"
    os.environ["AUTOBOT_ENV"] = "test"

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
async def redis_client(redis_url):
    """Provide Redis client for tests."""
    import redis.asyncio as redis

    client = redis.from_url(redis_url)
    yield client
    await client.close()


@pytest.fixture
async def http_client(backend_url):
    """Provide HTTP client for API tests."""
    import aiohttp

    async with aiohttp.ClientSession(base_url=backend_url) as session:
        yield session


# Test cleanup fixtures
@pytest.fixture(autouse=True, scope="function")
async def cleanup_after_test():
    """Cleanup after each test."""
    yield
    # Add any cleanup logic here
    # For example, clearing test data from Redis


# Test markers for selective execution
def pytest_configure(config):
    """Configure pytest with custom settings."""
    config.addinivalue_line("markers", "requires_redis: mark test as requiring Redis connection")
    config.addinivalue_line("markers", "requires_backend: mark test as requiring backend API")
    config.addinivalue_line("markers", "requires_vms: mark test as requiring distributed VMs")
