# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""Pytest fixtures for SLM testing."""

import sys
from pathlib import Path

# Add autobot-slm-backend to path for imports
slm_backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(slm_backend_root))

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from models.database import Base as SLMBase  # noqa: E402


@pytest.fixture(scope="function")
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)  # canonical: ignore py-adhoc-db-engine (test-local engine)
    # Use SLM Base for SLM tests
    SLMBase.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="function")
def db_session(in_memory_db):
    """Create a database session for testing."""
    SessionLocal = sessionmaker(bind=in_memory_db)  # canonical: ignore py-adhoc-db-engine (test-local session factory)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
