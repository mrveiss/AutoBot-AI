"""
AutoBot Test Suite Configuration
Provides pytest fixtures with configuration-driven test setup.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Dict, Any

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import configuration manager
from src.config import unified_config_manager


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
        "chroma": unified_config_manager.get_chroma_config(),
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
    config.addinivalue_line(
        "markers", "requires_redis: mark test as requiring Redis connection"
    )
    config.addinivalue_line(
        "markers", "requires_backend: mark test as requiring backend API"
    )
    config.addinivalue_line(
        "markers", "requires_vms: mark test as requiring distributed VMs"
    )
