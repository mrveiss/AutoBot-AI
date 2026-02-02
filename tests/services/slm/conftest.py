# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""Pytest fixtures for SLM testing."""

import sys
from pathlib import Path

# Add slm-server to path for imports (absolute path)
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "slm-server"))

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

try:
    from backend.models.infrastructure import Base as BackendBase  # noqa: E402
except ImportError:
    BackendBase = None

from models.database import Base as SLMBase  # noqa: E402


@pytest.fixture(scope="function")
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    # Use SLM Base for SLM tests
    SLMBase.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="function")
def db_session(in_memory_db):
    """Create a database session for testing."""
    SessionLocal = sessionmaker(bind=in_memory_db)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
