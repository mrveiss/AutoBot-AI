# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one audit action spelling map (#18716)."""

from enum import Enum

from autobot_shared.audit_actions import ACTION_ALIASES, canonical_action, spellings_of


class _Legacy(str, Enum):
    LOGIN = "login_success"


def test_aliases_resolve_and_unknown_spellings_pass_through() -> None:
    assert canonical_action("user.login") == "auth.login"
    assert canonical_action("api_key_request") == "api_key_request"  # a request decision, not a lifecycle event
    assert canonical_action("ai_line.change") == "ai_line.change"


def test_an_enum_member_is_read_by_value() -> None:
    assert canonical_action(_Legacy.LOGIN) == "auth.login"


def test_spellings_of_includes_the_canonical_form_and_every_alias() -> None:
    assert spellings_of("auth.login") >= {"auth.login", "login", "login_success", "login_successful", "user.login"}
    assert spellings_of("login") == spellings_of("auth.login")
    assert spellings_of("never.heard.of.it") == {"never.heard.of.it"}


def test_no_alias_chains() -> None:
    assert all(new not in ACTION_ALIASES for new in ACTION_ALIASES.values())
