# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM's ``UserService`` — the implementation lives in autobot_shared (#15068).

Not a re-export: this module binds the SLM's concrete ``User``. Both hooks keep
their shared no-op default — the SLM has no session store beyond the password
epoch, and owns no memory records to reassign. Error classes are imported from
``autobot_shared.user_management.user_service_errors``.
"""

from autobot_shared.user_management.user_service import UserService as SharedUserService
from user_management.models import User


class UserService(SharedUserService):
    """User service bound to the SLM's ``User``."""

    user_model = User
