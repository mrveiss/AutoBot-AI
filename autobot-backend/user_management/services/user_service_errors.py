# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Exceptions raised by ``UserService`` (split out of ``user_service.py``, #15736).

``user_service.py`` is a grandfathered oversized file (#14236) that may not
grow, so ``DuplicateUserError`` gaining a structured ``field`` attribute here
— rather than a docstring-only class inline in that file — is what keeps the
change from pushing it over its recorded ceiling. ``user_service.py``
re-exports every name below so existing ``from
user_management.services.user_service import DuplicateUserError``-style
imports keep working unchanged.
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
