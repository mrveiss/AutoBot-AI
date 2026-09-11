# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The transcriber's legacy owner id is a username no account may take (#15758)."""

from autobot_shared.user_management.schemas.user import RESERVED_USERNAMES
from transcriber.deps import DEFAULT_USER


def test_the_legacy_owner_id_is_a_reserved_username():
    """If DEFAULT_USER ever changes, user management must reserve the new value too.

    Otherwise an account could take it and own every pre-#15758 row. The
    request-time guard in resolve_user_id would still refuse it, but the
    clash belongs at account creation.
    """
    assert DEFAULT_USER in RESERVED_USERNAMES
