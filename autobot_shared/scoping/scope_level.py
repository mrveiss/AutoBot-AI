# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical visibility-scope enum for all shareable resources (#11277, #11290).

ONE enum for every subsystem that scopes resource visibility. Previously three
overlapping enums drifted in parallel (#11290); they are now thin aliases of
this class:

- ``models.secret.SecretScope``        — persists ``secrets.scope`` rows
- ``knowledge.ownership.VisibilityLevel`` — persists knowledge fact metadata
- ``ScopeLevel`` (here)                — skills/agents resource scoping

The ``.value`` strings below are PERSISTED in DB rows and Redis metadata.
NEVER rename a value; add new members instead. Members are a documented
superset — each subsystem uses the subset that its storage layer documents:

Common core (all subsystems): user, session*, shared, group, organization
Secrets-only: workflow (#2153)
Knowledge-only: private, system, public (#679)

*knowledge does not persist ``session``; secrets/skills do.
"""

from enum import Enum


class ScopeLevel(str, Enum):
    """Visibility scope for a shareable resource (secret, knowledge fact, skill, agent)."""

    # --- common core ---
    USER = "user"  # Only accessible by owner (private to the owning user)
    SESSION = "session"  # Only accessible in a specific session
    SHARED = "shared"  # Explicitly shared with specific users
    GROUP = "group"  # Accessible to group/team members
    ORGANIZATION = "organization"  # Accessible to all org/company members

    # --- secrets-only (persisted in secrets.scope; Issue #2153) ---
    WORKFLOW = "workflow"  # Scoped to a specific workflow

    # --- knowledge-only (persisted in fact metadata; Issue #679) ---
    PRIVATE = "private"  # Only owner can access (knowledge's spelling of USER)
    SYSTEM = "system"  # Platform-wide, accessible to all authenticated users
    PUBLIC = "public"  # Alias-semantics of SYSTEM (backward compatibility)

    @classmethod
    def default(cls) -> "ScopeLevel":
        """Default scope for new resources: company-wide."""
        return cls.ORGANIZATION
