# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
User Model

Core user model with authentication, profile, and tenant association.

The implementation now lives in
``autobot_shared.user_management.models.user.UserCore`` (#12647). SLM's user
model was a strict subset of backend's, so nothing SLM-specific remains here —
only the concrete table mapping, which each backend must own separately
because backend attaches activity-tracking relationships (#871) whose target
models do not exist in SLM's registry.

Kept as a concrete class in this module, not a re-export, so every existing
``from user_management.models.user import User`` importer keeps working
unchanged.
"""

from autobot_shared.user_management.models.user import UserCore


class User(UserCore):
    """SLM's concrete ``users`` mapping.

    All columns, relationships and helpers come from ``UserCore`` — see
    ``autobot_shared/user_management/models/user.py`` for their documentation.
    """

    __tablename__ = "users"
