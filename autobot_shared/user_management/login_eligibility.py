# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one rule for whether an account may start a session, by any login method (#18338).

Password login applies it in ``UserAccessMixin._validate_user_can_login``; SSO applies it
through ``sso_account_policy`` before a token is minted. Kept free of imports so the SSO
service, whose tests load it under stubbed database packages, can use the same function.
"""

from typing import Any


def login_refusal(user: Any) -> str | None:
    """Why *user* may not start a session, or None: deleted accounts and inactive ones are refused."""
    if getattr(user, "deleted_at", None) is not None:
        return "account_deleted"
    if not user.is_active:
        return "account_inactive"
    return None
