# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Negative fixture: obtains a session from the canonical factory."""

from user_management.database import get_async_session_factory

Session = get_async_session_factory()
