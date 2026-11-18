# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared FastAPI dependencies of the SSO routers (#17312)."""

from services.database import get_db


async def get_audit_db():
    """Dependency for the audit (main SLM security) database session."""
    async for session in get_db():
        yield session
