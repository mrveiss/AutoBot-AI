# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reserved usernames are refused when an account is created or renamed (#15758)."""

import pytest
from pydantic import ValidationError

from autobot_shared.user_management.schemas.user import RESERVED_USERNAMES, UserCreate, UserUpdate

# No credential field: it is optional (SSO accounts) and these tests are about
# the username. A literal value would also read as a secret to detect-secrets.
_VALID = {"email": "someone@example.com"}


@pytest.mark.parametrize("name", ["default", "Default", "DEFAULT"])
def test_an_account_cannot_be_created_with_a_reserved_username(name):
    with pytest.raises(ValidationError, match="reserved"):
        UserCreate(username=name, **_VALID)


@pytest.mark.parametrize("name", ["default", "Default"])
def test_an_account_cannot_be_renamed_to_a_reserved_username(name):
    with pytest.raises(ValidationError, match="reserved"):
        UserUpdate(username=name)


def test_an_ordinary_username_is_still_accepted_and_lowercased():
    """The contrast case: the reservation refuses only the reserved names."""
    assert UserCreate(username="Default_User", **_VALID).username == "default_user"
    assert UserUpdate(username="Carol").username == "carol"


def test_the_format_rule_still_applies():
    with pytest.raises(ValidationError, match="letters, numbers, and underscores"):
        UserCreate(username="bad-name", **_VALID)


def test_the_reserved_set_is_not_empty():
    """Keeps the reservation tests above from going vacuous."""
    assert "default" in RESERVED_USERNAMES
