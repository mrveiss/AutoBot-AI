# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
WorkflowSharingService (#2165)

Manages workflow sharing via Redis-backed share records.  Each share is
identified by a randomly-generated share_id that can be handed to other
users or published publicly.

Share records are stored in the 'workflows' Redis database under the key
  autobot:workflow_share:<share_id>
with an optional TTL (default: 30 days for public shares, no TTL for
targeted user shares so the owner can revoke explicitly).

An index key
  autobot:workflow_share_idx:<workflow_id>
tracks all share_ids for a given workflow so the owner can list/revoke them.

Usage:
    from services.workflow_sharing_service import WorkflowSharingService
    from services.workflow_serializer import WorkflowSerializer

    sharing = WorkflowSharingService(serializer)

    # Share publicly
    share_id = await sharing.share_workflow("wf-abc123", public=True)

    # Share with a specific user
    share_id = await sharing.share_workflow("wf-abc123", target_user_id="user-xyz")

    # Clone a shared workflow for a different owner
    new_id = await sharing.clone_workflow(share_id, new_owner_id="user-xyz")

    # Revoke a share
    await sharing.unshare_workflow(share_id)

    # List all shares visible to a user
    shares = await sharing.list_shared(user_id="user-xyz")
"""

import json
import uuid
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import utc_timestamp
from services.workflow_serializer import WorkflowSerializer

logger = get_logger(__name__)

# Redis key prefixes
_SHARE_KEY_PREFIX = "autobot:workflow_share"
_INDEX_KEY_PREFIX = "autobot:workflow_share_idx"

# Default TTL for public shares: 30 days in seconds
_PUBLIC_SHARE_TTL = 30 * 24 * 60 * 60


# ---------------------------------------------------------------------------
# Share record
# ---------------------------------------------------------------------------


def _share_record(
    share_id: str,
    workflow_id: str,
    owner_id: str,
    public: bool,
    target_user_id: str | None,
    export_doc: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the share record dict stored in Redis (pure helper)."""
    return {
        "share_id": share_id,
        "workflow_id": workflow_id,
        "owner_id": owner_id,
        "public": public,
        "target_user_id": target_user_id,
        "created_at": utc_timestamp() + "Z",
        "workflow": export_doc,
    }


def _share_key(share_id: str) -> str:
    """Redis key for a share record (pure helper)."""
    return f"{_SHARE_KEY_PREFIX}:{share_id}"


def _index_key(workflow_id: str) -> str:
    """Redis key for the share-id index of a workflow (pure helper)."""
    return f"{_INDEX_KEY_PREFIX}:{workflow_id}"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class WorkflowSharingService:
    """
    Redis-backed workflow sharing (#2165).

    Depends on a WorkflowSerializer to export workflows before storing them.
    All Redis operations use the 'workflows' database.
    """

    def __init__(self, serializer: WorkflowSerializer) -> None:
        self._serializer = serializer

    # ------------------------------------------------------------------
    # Share
    # ------------------------------------------------------------------

    async def share_workflow(
        self,
        workflow_id: str,
        owner_id: str,
        target_user_id: str | None = None,
        public: bool = False,
    ) -> str | None:
        """
        Create a new share for *workflow_id*.

        At least one of *target_user_id* or *public=True* must be provided.

        Args:
            workflow_id: ID of the workflow to share.
            owner_id: ID of the user sharing the workflow.
            target_user_id: Specific user to share with.  None for public.
            public: When True the share is open to any authenticated user.

        Returns:
            share_id string on success, None on failure.
        """
        if not public and not target_user_id:
            logger.warning(
                "share_workflow: must specify target_user_id or public=True for workflow %s",
                workflow_id,
            )
            return None

        export_doc = await self._serializer.export_workflow(workflow_id)
        if export_doc is None:
            logger.warning("share_workflow: workflow %s not found or not exportable", workflow_id)
            return None

        share_id = str(uuid.uuid4())
        record = _share_record(
            share_id=share_id,
            workflow_id=workflow_id,
            owner_id=owner_id,
            public=public,
            target_user_id=target_user_id,
            export_doc=export_doc.to_dict(),
        )

        redis = await get_async_redis_client(database="workflows")
        if redis is None:
            logger.error("share_workflow: Redis unavailable for workflow %s", workflow_id)
            return None

        key = _share_key(share_id)
        payload = json.dumps(record, ensure_ascii=False)

        if public:
            await redis.setex(key, _PUBLIC_SHARE_TTL, payload)
        else:
            await redis.set(key, payload)

        # Maintain index: owner can list/revoke all shares for a workflow
        await redis.sadd(_index_key(workflow_id), share_id)

        logger.info(
            "Workflow %s shared as %s (public=%s target=%s) by owner=%s",
            workflow_id,
            share_id,
            public,
            target_user_id,
            owner_id,
        )
        return share_id

    # ------------------------------------------------------------------
    # Unshare
    # ------------------------------------------------------------------

    async def unshare_workflow(self, share_id: str) -> bool:
        """
        Revoke a share by deleting its record from Redis.

        Args:
            share_id: The share to revoke.

        Returns:
            True when the share existed and was deleted, False otherwise.
        """
        redis = await get_async_redis_client(database="workflows")
        if redis is None:
            logger.error("unshare_workflow: Redis unavailable for share %s", share_id)
            return False

        key = _share_key(share_id)
        raw = await redis.get(key)
        if not raw:
            logger.warning("unshare_workflow: share %s not found", share_id)
            return False

        record = json.loads(raw)
        workflow_id = record.get("workflow_id", "")

        await redis.delete(key)
        if workflow_id:
            await redis.srem(_index_key(workflow_id), share_id)

        logger.info("Share %s (workflow=%s) revoked", share_id, workflow_id)
        return True

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_shared(self, user_id: str | None = None) -> List[Dict[str, Any]]:
        """
        Return share records visible to *user_id*.

        A record is visible when:
        - it is public, OR
        - it targets *user_id* specifically, OR
        - *user_id* is the owner.

        When *user_id* is None, all public shares are returned.

        Args:
            user_id: Requesting user's ID.

        Returns:
            List of share record dicts (without the embedded workflow payload
            to keep the response lightweight).
        """
        redis = await get_async_redis_client(database="workflows")
        if redis is None:
            logger.error("list_shared: Redis unavailable")
            return []

        # Scan for all share keys
        visible: List[Dict[str, Any]] = []
        cursor = 0
        pattern = f"{_SHARE_KEY_PREFIX}:*"

        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=200)
            for key in keys:
                raw = await redis.get(key)
                if not raw:
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("list_shared: corrupt share record at key %s", key)
                    continue

                if self._is_visible_to(record, user_id):
                    visible.append(_strip_workflow_payload(record))

            if cursor == 0:
                break

        logger.debug("list_shared: found %s visible shares for user=%s", len(visible), user_id)
        return visible

    # ------------------------------------------------------------------
    # Clone
    # ------------------------------------------------------------------

    async def clone_workflow(
        self,
        share_id: str,
        new_owner_id: str | None,
        session_id: str | None = None,
    ) -> str | None:
        """
        Import a shared workflow and assign it to *new_owner_id*.

        Args:
            share_id: Share to clone from.
            new_owner_id: ID of the user who will own the cloned workflow.
            session_id: Optional session to attach to the cloned workflow.

        Returns:
            New workflow_id on success, None on failure.
        """
        redis = await get_async_redis_client(database="workflows")
        if redis is None:
            logger.error("clone_workflow: Redis unavailable for share %s", share_id)
            return None

        raw = await redis.get(_share_key(share_id))
        if not raw:
            logger.warning("clone_workflow: share %s not found", share_id)
            return None

        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("clone_workflow: corrupt share record %s", share_id)
            return None

        export_doc = record.get("workflow")
        if not export_doc:
            logger.error("clone_workflow: share %s has no embedded workflow", share_id)
            return None

        new_id = await self._serializer.import_workflow(
            data=export_doc,
            owner_id=new_owner_id,
            session_id=session_id,
        )

        if new_id:
            logger.info(
                "Cloned share %s as workflow %s for owner=%s",
                share_id,
                new_id,
                new_owner_id,
            )
        else:
            logger.warning(
                "clone_workflow: import failed for share %s owner=%s",
                share_id,
                new_owner_id,
            )

        return new_id

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_visible_to(record: Dict[str, Any], user_id: str | None) -> bool:
        """Return True when the share record is visible to *user_id* (pure helper)."""
        if record.get("public"):
            return True
        if user_id is None:
            return False
        return record.get("owner_id") == user_id or record.get("target_user_id") == user_id


def _strip_workflow_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *record* without the embedded workflow dict (pure helper)."""
    return {k: v for k, v in record.items() if k != "workflow"}
