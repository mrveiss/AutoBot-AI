# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Redis MCP router decides admin with the one predicate (#16333).

Its literal ``role in ("admin", "superadmin")`` refused "Admin" and a ``Role`` member that the
rest of the backend admits.
"""

from api.redis_mcp.router import _is_admin
from autobot_shared.auth.permissions import Role


def test_admins_in_any_spelling():
    for role in ("admin", "superadmin", "Admin", "SUPERADMIN", Role.ADMIN):
        assert _is_admin({"role": role}), role


def test_non_admins_and_no_role():
    for user in ({"role": "user"}, {"role": "service"}, {}, {"role": None}):
        assert not _is_admin(user), user
