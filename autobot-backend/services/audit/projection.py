# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Redis projection of the audit trail (#17225).

The trail's system of record is Postgres ``audit_logs`` (``store.py``); these
keys are a rebuildable copy (``audit.rebuild_projection``) and are never read
as the answer to an audit question. ``audit:unified`` holds every event; ``audit:category:<category>`` holds one
category each, with the TTL the retention table (``retention.py``) assigns it.
This is the ONLY code that writes an ``audit:`` key in the backend's main Redis
database -- the guard ``repo_tests/audit_writer_single_source_17225_test.py``
fails on a second one.
"""

import json
from typing import Any

from autobot_shared.store_authority import system_of_record
from services.audit.retention import ttl_seconds
from services.audit.taxonomy import AuditCategory, AuditEvent

# #17225 D1: the trail is durable in Postgres audit_logs (store.py); these keys
# are its projection -- see autobot_shared/store_authority.py.
SYSTEM_OF_RECORD = system_of_record("audit_trail")

UNIFIED_KEY = "audit:unified"
_CATEGORY_KEY_PREFIX = "audit:category:"


def category_key(category: AuditCategory) -> str:
    """The per-category projection key."""
    return f"{_CATEGORY_KEY_PREFIX}{category.value}"


async def write_event(redis: Any, event: AuditEvent) -> None:
    """Project one event onto the unified and per-category sorted sets."""
    raw = json.dumps(event.to_dict(), ensure_ascii=False)
    cat_key = category_key(event.category)
    async with redis.pipeline() as pipe:
        await pipe.zadd(UNIFIED_KEY, {raw: event.occurred_at})
        # UNIFIED_KEY spans categories with different retention -- never expire
        # it (#8303); the nightly purge trims it at the longest period.
        await pipe.zadd(cat_key, {raw: event.occurred_at})
        await pipe.expire(cat_key, ttl_seconds(event.category))
        await pipe.execute()
