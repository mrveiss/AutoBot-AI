# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from autobot_shared.scoping.scope_level import ScopeLevel


def test_scope_level_members_mirror_secrets():
    assert {s.value for s in ScopeLevel} == {"user", "session", "shared", "group", "organization"}


def test_default_is_organization():
    assert ScopeLevel.default() is ScopeLevel.ORGANIZATION
