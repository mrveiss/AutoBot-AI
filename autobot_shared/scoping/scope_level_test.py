# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from autobot_shared.scoping.scope_level import ScopeLevel

# Stored-value safety (#11290): these strings are persisted in secrets.scope
# rows and knowledge fact metadata. Renaming any of them corrupts stored data.
_FROZEN_STORED_VALUES = {
    "USER": "user",
    "SESSION": "session",
    "SHARED": "shared",
    "GROUP": "group",
    "ORGANIZATION": "organization",
    "WORKFLOW": "workflow",
    "PRIVATE": "private",
    "SYSTEM": "system",
    "PUBLIC": "public",
}


def test_members_are_canonical_superset():
    assert {m.name: m.value for m in ScopeLevel} == _FROZEN_STORED_VALUES


def test_secret_scope_subset_values_frozen():
    """Values persisted by secrets.scope (models.secret.SecretScope)."""
    persisted = {"user", "session", "shared", "group", "organization", "workflow"}
    assert persisted <= {m.value for m in ScopeLevel}


def test_knowledge_visibility_subset_values_frozen():
    """Values persisted in knowledge fact metadata (VisibilityLevel)."""
    persisted = {"private", "shared", "group", "organization", "system", "public"}
    assert persisted <= {m.value for m in ScopeLevel}


def test_default_is_organization():
    assert ScopeLevel.default() is ScopeLevel.ORGANIZATION
