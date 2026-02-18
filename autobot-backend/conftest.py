"""
AutoBot User Backend - Test Configuration
Provides pytest fixtures for colocated tests.

Issue: #734 - Colocate tests with source files
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Ensure autobot-user-backend is importable
project_root = Path(__file__).parent.parent
backend_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(backend_root))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_data_dir() -> Path:
    """Get test data directory."""
    return Path(__file__).parent / "tests" / "fixtures" / "data"


@pytest.fixture
def temp_dir(tmp_path) -> Path:
    """Provide temporary directory for test files."""
    return tmp_path


@pytest.fixture(autouse=True)
def set_test_environment():
    """
    Set TEST environment variables for all tests.
    Prevents tests from affecting production data.
    """
    original_env = dict(os.environ)

    os.environ["AUTOBOT_TEST_MODE"] = "true"
    os.environ["AUTOBOT_ENV"] = "test"

    yield

    os.environ.clear()
    os.environ.update(original_env)
