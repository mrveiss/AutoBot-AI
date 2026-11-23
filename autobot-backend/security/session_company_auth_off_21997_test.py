# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Assigning a chat to a company on an install without authentication (#21997).

``_resolve_company_scope`` gives an auth-off caller no scope and no refusal; ``may_act_in_company`` (behind the
assign route and a named company at creation) answers the same way instead of refusing every caller for lacking a
user id. An authenticated caller with no user id is still refused.
"""

import uuid
from unittest.mock import MagicMock, patch

from security.session_company import may_act_in_company

CO = uuid.uuid4()


def _auth(enabled: bool):
    return patch("auth_middleware.get_auth_middleware", return_value=MagicMock(enable_auth=enabled))


class TestMayActWithAuthOff:
    async def test_a_caller_flagged_auth_disabled_may_act(self):
        with _auth(True):
            assert await may_act_in_company(CO, {"auth_disabled": True}) is True

    async def test_authentication_off_in_the_middleware_may_act_without_a_user_id(self):
        with _auth(False):
            assert await may_act_in_company(CO, {}) is True

    async def test_an_authenticated_caller_without_a_user_id_is_still_refused(self):
        with _auth(True), patch("api.user_management.dependencies._is_platform_admin_claim", return_value=False):
            assert await may_act_in_company(CO, {}) is False
