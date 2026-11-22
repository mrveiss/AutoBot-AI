# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19125: the SLM ``admin`` claim covers the whole admin role family."""

import pytest

from services import jwks_verifier


@pytest.mark.parametrize(
    ("role", "expected"),
    [("admin", True), ("superadmin", True), ("operator", False), ("user", False)],
)
def test_normalize_claims_admin_flag_covers_the_admin_family(role, expected):
    """#19125: superadmin is the highest form of admin, so /me reports is_admin for it."""
    result = jwks_verifier._normalize_claims({"sub": "u", "role": role})
    assert result["admin"] is expected
