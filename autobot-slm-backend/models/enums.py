# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Status enumerations for the SLM data model.

Extracted verbatim from models/database.py, which sat at exactly its recorded
size ceiling (1229/1229). ``scripts/python_file_size_known_large.py`` says that
mapping ONLY SHRINKS -- "never add an entry to make a new file pass; split the
file instead" -- so the block had to move out before anything could be added.

Scope is the contiguous run of enums that preceded the first mapped class. The
enums defined further down database.py stay there: each sits with the model
whose column it constrains, and pulling them out would separate them from it.
These seven constrained nothing local, which is why they were already grouped.

``models.database`` re-exports every name here, so existing imports keep
working unchanged -- this is a pure move with no behaviour change.
"""

from __future__ import annotations

import enum


class NodeStatus(str, enum.Enum):
    """Node status enumeration."""

    PENDING = "pending"
    ENROLLING = "enrolling"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"


class DeploymentStatus(str, enum.Enum):
    """Deployment status enumeration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class BackupStatus(str, enum.Enum):
    """Backup status enumeration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CodeStatus(str, enum.Enum):
    """Code version status (Issue #741)."""

    UP_TO_DATE = "up_to_date"
    OUTDATED = "outdated"
    CODE_CURRENT_SERVICE_FAILED = "code_current_service_failed"  # #1605
    UNKNOWN = "unknown"


class RoleStatus(str, enum.Enum):
    """Role detection status (Issue #779)."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    NOT_INSTALLED = "not_installed"


class SyncType(str, enum.Enum):
    """Code sync type (Issue #779)."""

    COMPONENT = "component"
    PACKAGE = "package"


class BackupServiceType(str, enum.Enum):
    """Data service a backup, replication or verification targets (#13578).

    ``service_type`` was the outlier among the eight sibling enums in this
    module: a bare ``String(32)`` with no constraint anywhere. The cost landed
    the moment a second engine arrived — the dispatch table in
    ``api/stateful.py`` had to accept two spellings of the same engine, and an
    unknown value was not rejected at the API boundary at all. It reached
    ``_run_backup``, wrote a ``Backup`` row, and only then failed, leaving a
    ``BackupStatus.FAILED`` row for a typo that is indistinguishable from one
    for a real failure.

    The column stays a string at rest (#13578: existing rows keep working);
    this enum is the boundary that decides what may enter.
    """

    REDIS = "redis"
    POSTGRES = "postgres"

    @classmethod
    def _missing_(cls, value: object) -> "BackupServiceType | None":
        """Accept ``postgresql`` as a spelling of ``postgres``.

        Both spellings were live keys in the backup dispatch table, so both are
        already in stored ``backups.service_type`` values and in whatever
        callers send. Resolving the alias here keeps every old spelling parsing
        without a second class to keep in step — and collapses it to one
        canonical member at the boundary, so nothing downstream branches twice.
        """
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        if normalized in _BACKUP_SERVICE_TYPE_ALIASES:
            return _BACKUP_SERVICE_TYPE_ALIASES[normalized]
        # Case only. Without this the resolution is inconsistent in a way that
        # reads as a bug from outside: "POSTGRESQL" would resolve through the
        # alias table while "POSTGRES" — the canonical spelling — would 422.
        for member in cls:
            if member.value == normalized:
                return member
        return None


# Wire spellings that are not member values. Kept next to the enum so the set of
# accepted inputs is one greppable place rather than a dispatch-table key.
_BACKUP_SERVICE_TYPE_ALIASES: dict[str, BackupServiceType] = {
    "postgresql": BackupServiceType.POSTGRES,
}
