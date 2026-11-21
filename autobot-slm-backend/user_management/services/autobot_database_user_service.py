# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The user service for the ``autobot_users`` database, whose tokens the backend verifies (#20443)."""

from user_management.services.user_service import UserService


class AutobotDatabaseUserService(UserService):
    """User service over the ``autobot_users`` database, whose users sign in to the main backend (#20443).

    The backend verifies those tokens against Redis, while this process keeps its own password
    epochs in the SLM database (#18663): a revocation written there would never reach the backend.
    """

    epoch_in_redis = True
