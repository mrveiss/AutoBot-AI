# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Exceptions raised by ``UserService``, shared by both backends (#15068).

Split out of the backend's ``user_service.py`` in #15736, when
``DuplicateUserError`` gained a structured ``field``. The SLM's copy defined the
same four classes inline without ``field``; this superset is now the only
definition, so a caller in either service can name the conflicting field
without echoing the value back.
"""

from __future__ import annotations


class UserServiceError(Exception):
    """Base exception for user service errors."""


class UserNotFoundError(UserServiceError):
    """Raised when user is not found."""


class DuplicateUserError(UserServiceError):
    """Raised on a duplicate user; carries the conflicting ``field`` so a
    caller can name the conflict without echoing the value back (#15736)."""

    def __init__(self, message: str, field: str):
        super().__init__(message)
        self.field = field


class InvalidCredentialsError(UserServiceError):
    """Raised when authentication fails."""


class SessionReassignError(UserServiceError):
    """Raised when a removed user's chat sessions cannot all be handed to a successor (#20029).

    No successor and no active administrator, or an owner write that failed. The removal is refused, so a
    session is never left owned by an account that can no longer act.
    """

    status_code = 409


class SessionStoreWriteError(SessionReassignError):
    """A session's owner could not be written: a store fault, not a missing successor."""

    status_code = 503
