# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one mapping from every historical audit action spelling to the canonical one (#18716).

The canonical spelling is the dotted ``<resource>.<verb>`` form (owner decision,
2026-10-20), and its vocabulary is ``AuditAction`` in
``autobot-backend/services/audit/taxonomy.py``. That enum lives in the backend,
which this package must not import, so the *mapping* lives here and the enum
holds the targets; ``repo_tests/audit_action_vocabulary_18716_test.py`` fails when
a target below is not a member.

The mapping is used in two directions:

* write boundary -- :func:`canonical_action` is applied where a writer owns a
  public vocabulary it cannot change (``IdentityAuditAction`` of the shared
  user-management package, ``ComplianceEventType`` of the admin event-log API),
  so the stored row carries the canonical spelling;
* read boundary -- :func:`spellings_of` expands a canonical action into itself
  plus every alias, so rows stored before this change still match.

``ACTION_ALIASES`` is a transition table. Stored ``audit_logs`` rows are only
rewritten through the approved data migration (approval queue, #17038); once it
has run, the aliases that exist solely for stored rows are removed and the
read-side expansion collapses to the canonical spelling.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

#: old spelling -> canonical spelling. Keep one line per concept so a diff reads as a decision.
ACTION_ALIASES: dict[str, str] = {
    # login: one attempt, success or failure; the outcome column carries which
    **dict.fromkeys(
        (
            "login",
            "login_success",
            "login_successful",
            "login_attempt",
            "login_attempt_locked_account",
            "login_failed",
            "sso_login",
            "user.login",
        ),
        "auth.login",
    ),
    **dict.fromkeys(("logout", "user.logout"), "auth.logout"),
    **dict.fromkeys(("config.changed", "config.change", "settings_updated"), "config.update"),
    **dict.fromkeys(("file_delete", "conversation_file_delete", "document.deleted"), "file.delete"),
    **dict.fromkeys(("file_upload", "document.uploaded"), "file.upload"),
    "file_download": "file.download",
    "file_create": "file.create",
    **dict.fromkeys(("user_created", "user.created"), "user.create"),
    "user_deleted": "user.delete",
    "user_updated": "user.update",
    "role_assigned": "role.assign",
    "role_revoked": "role.revoke",
    "user.role_changed": "role.change",
    "password_changed": "password.change",  # nosec B105  # pragma: allowlist secret -- an action name
    **dict.fromkeys(("api_key_created", "api_key.created"), "api_key.create"),  # pragma: allowlist secret
    **dict.fromkeys(("api_key_revoked", "api_key.deleted"), "api_key.revoke"),  # pragma: allowlist secret
}


def _spelling(action: Any) -> str:
    return str(action.value if isinstance(action, Enum) else action)


def canonical_action(action: Any) -> str:
    """The canonical spelling of *action* (an enum member or a string); unknown spellings pass through."""
    spelling = _spelling(action)
    return ACTION_ALIASES.get(spelling, spelling)


def spellings_of(action: Any) -> frozenset[str]:
    """*action*'s canonical spelling plus every spelling that maps onto it (the read-side match set)."""
    canonical = canonical_action(action)
    return frozenset({canonical, *(old for old, new in ACTION_ALIASES.items() if new == canonical)})
