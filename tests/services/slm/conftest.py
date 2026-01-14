# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""Pytest fixtures for SLM testing."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.models.infrastructure import Base


@pytest.fixture(scope="function")
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
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
