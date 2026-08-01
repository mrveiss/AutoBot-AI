# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Single source of truth for a node's current-vs-latest code_status label.

Extracted from api/nodes.py (#12428/#12570) into a shared, dependency-light
module so api/updates.py can reuse the exact same derivation without a
nodes<->updates circular import (#12571). Every surface that reports a
node's code currency -- GET /nodes, GET /nodes/{id}, GET /nodes/{id}/updates,
and the #11964 fleet-update badge (GET /updates/fleet-summary) -- must go
through these functions so none of them can disagree.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import CodeStatus, Node, Setting


def derive_code_status(
    code_version: str | None,
    latest_version: str | None,
    was_service_failed: bool = False,
) -> str | None:
    """Pure function: the CodeStatus label for code_version vs latest_version.

    Single source of truth for a node's currency label (#12428): mirrors the
    live signal ``outdated_nodes`` already uses (api/code_sync.py
    get_sync_status, ``code_version != latest_version``) so a node's
    reported code_status can never disagree with the fleet-wide outdated
    count. Shared by write time (api.nodes._update_heartbeat_code_status, on
    a heartbeat) and read time (reported_code_status, on every GET) -- an
    agentless node that never heartbeats still gets a fresh label on read.

    Returns None when latest_version is unknown -- callers should fall back
    to whatever status is already on hand (mirrors get_sync_status's own
    fallback when the fleet latest commit isn't set yet).

    was_service_failed preserves the #1605 code_current_service_failed
    signal when the version still matches latest; that check needs live
    heartbeat extra_data and cannot be recomputed at read time, so a read
    derivation passes in the node's own last-known stamp instead.
    """
    if not latest_version:
        return None
    if not code_version:
        return CodeStatus.UNKNOWN.value
    if code_version != latest_version:
        return CodeStatus.OUTDATED.value
    if was_service_failed:
        return CodeStatus.CODE_CURRENT_SERVICE_FAILED.value
    return CodeStatus.UP_TO_DATE.value


async def get_latest_code_version(db: AsyncSession) -> str | None:
    """Read the fleet's slm_agent_latest_commit setting.

    Same query used by api.nodes._update_heartbeat_code_status and
    api/code_sync.py's get_sync_status -- kept here so every reader compares
    against the exact same live value (#12428/#12571).
    """
    result = await db.execute(select(Setting).where(Setting.key == "slm_agent_latest_commit"))
    setting = result.scalar_one_or_none()
    return setting.value if setting else None


def reported_code_status(node: Node, latest_version: str | None) -> str | None:
    """Derive the code_status to report for a node READ (#12428).

    node.code_status is a stamp written only by
    api.nodes._update_heartbeat_code_status, which runs only on a heartbeat.
    An agentless node (e.g. role vnc) never heartbeats, so the stamp
    freezes -- often at up_to_date from enrollment -- even after
    code_version drifts behind latest_version, disagreeing with
    outdated_nodes (api/code_sync.py get_sync_status), which always uses the
    live code_version != latest_version signal. Recomputing here on every
    read keeps every surface (GET /nodes, GET /nodes/{id},
    GET /nodes/{id}/updates, GET /updates/fleet-summary) in agreement; falls
    back to the stored stamp when latest_version is unknown.
    """
    derived = derive_code_status(
        node.code_version,
        latest_version,
        was_service_failed=node.code_status == CodeStatus.CODE_CURRENT_SERVICE_FAILED.value,
    )
    return derived if derived is not None else node.code_status
