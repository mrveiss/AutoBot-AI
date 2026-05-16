# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Canonical SQLAlchemy sync session lifecycle helper (GH#7441).

Provides session_scope() for sync callers that need commit-on-exit,
rollback-on-error, and guaranteed close semantics in one place.

Async callers use db_session_context() from user_management.database.
"""

from contextlib import contextmanager
from typing import Callable, Generator

from sqlalchemy.orm import Session


@contextmanager
def session_scope(session_factory: Callable[[], Session]) -> Generator[Session, None, None]:
    """Canonical sync session context manager.

    Commits on clean exit, rolls back on any exception, and always closes.
    Eliminates bare ``session_factory()`` calls that lack rollback protection.

    Args:
        session_factory: A SQLAlchemy ``sessionmaker`` instance (or any
            zero-argument callable returning a ``Session``).

    Usage::

        with session_scope(SessionLocal) as session:
            session.add(obj)
    """
    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
