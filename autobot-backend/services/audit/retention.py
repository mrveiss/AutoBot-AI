# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one audit retention policy table (#17225 D5).

Before #17225 every audit writer carried its own retention: ``audit.py`` per
category, ``audit_log.py`` 90 days, ``event_log.py`` 90 days,
``knowledge/audit_log.py`` per instance, ``audit_logger.py`` a config value, and
``security_layer.py`` and ``workflow_audit_log`` none at all. This table is the
only place a retention period for an audit record is decided. The Redis
projection's key TTLs and the nightly purge (``tasks/audit_log_retention.py``)
both read it, so the two cannot disagree.

Each period is an env-backed module constant
(``AUTOBOT_AUDIT_<CATEGORY>_RETENTION_DAYS``); the defaults are the per-category
values ``audit.py`` already applied.
"""

import time
from typing import Dict

from autobot_shared.env_utils import env_int_clamped
from services.audit.taxonomy import AuditCategory

_SECONDS_PER_DAY = 24 * 3600

#: Defaults, in days -- unchanged from audit.py's former _CATEGORY_TTL.
_DEFAULT_RETENTION_DAYS: Dict[AuditCategory, int] = {
    AuditCategory.SECURITY: 90,
    AuditCategory.COMPLIANCE: 90,
    AuditCategory.KNOWLEDGE: 365,
    AuditCategory.GOVERNANCE: 365,
}


def _env_name(category: AuditCategory) -> str:
    return f"AUTOBOT_AUDIT_{category.name}_RETENTION_DAYS"


#: The policy table: category -> days a record of that category is kept.
RETENTION_DAYS: Dict[AuditCategory, int] = {
    cat: env_int_clamped(_env_name(cat), default, min_v=1) for cat, default in _DEFAULT_RETENTION_DAYS.items()
}

#: The longest period in the table. The unified projection key spans every
#: category, so it can only be trimmed at the longest one (#8303).
LONGEST_RETENTION_DAYS: int = max(RETENTION_DAYS.values())


def ttl_seconds(category: AuditCategory) -> int:
    """Seconds a record of *category* is retained."""
    return RETENTION_DAYS[category] * _SECONDS_PER_DAY


def cutoff_ts(days: int, now: float | None = None) -> float:
    """Unix timestamp before which a record kept for *days* has expired."""
    return (time.time() if now is None else now) - days * _SECONDS_PER_DAY
