# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Version History and Rollback (#2145)

Provides Redis-backed version history for workflow definitions.  Each saved
version is a full snapshot of the workflow data at a point in time.  Versions
are auto-incremented per workflow and stored in two Redis structures:

  workflow:versions:{workflow_id}:list   — sorted set; member = version number
                                           (as string), score = version number
  workflow:versions:{workflow_id}:{ver}  — JSON string; full version record

Usage:
    from services.workflow_versioning import WorkflowVersionStore

    store = WorkflowVersionStore()

    # Snapshot the current state before a change
    version = await store.save_version("wf-abc123", data, notes="before refactor")

    # List all saved versions (newest first)
    summaries = await store.list_versions("wf-abc123")

    # Retrieve a specific snapshot
    wv = await store.get_version("wf-abc123", version=2)

    # Restore a snapshot (returns the stored data dict)
    restored = await store.restore_version("wf-abc123", version=1)

    # Compare two snapshots
    diff = await store.diff_versions("wf-abc123", v1=1, v2=2)

    # Delete a version
    deleted = await store.delete_version("wf-abc123", version=1)
"""

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import utc_timestamp as _utc_now

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Redis key helpers
# ---------------------------------------------------------------------------

_KEY_PREFIX = "workflow:versions"


def _list_key(workflow_id: str) -> str:
    """Sorted-set key that tracks all version numbers for *workflow_id*."""
    return f"{_KEY_PREFIX}:{workflow_id}:list"


def _version_key(workflow_id: str, version: int) -> str:
    """JSON-string key for the full record of a specific version."""
    return f"{_KEY_PREFIX}:{workflow_id}:{version}"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class WorkflowVersion:
    """Immutable snapshot of a workflow at a given version (#2145)."""

    workflow_id: str
    version: int
    data: Dict[str, Any]
    created_at: str  # ISO-8601 UTC timestamp
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "WorkflowVersion":
        """Reconstruct from a stored record dict."""
        return cls(
            workflow_id=raw["workflow_id"],
            version=int(raw["version"]),
            data=raw.get("data", {}),
            created_at=raw["created_at"],
            notes=raw.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class WorkflowVersionStore:
    """
    Redis-backed workflow version store (#2145).

    All operations are async and use the 'workflows' Redis database for
    consistency with the rest of the workflow services.  Every public method
    returns a safe value (None / False / []) when Redis is unavailable.
    """

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def save_version(
        self,
        workflow_id: str,
        data: Dict[str, Any],
        notes: str = "",
    ) -> int | None:
        """
        Persist *data* as the next version of *workflow_id* (#2145).

        The version number is auto-incremented: if the workflow already has
        versions [1, 2, 3] the new version will be 4.  Version numbering
        starts at 1.

        Args:
            workflow_id: Workflow being snapshotted.
            data: Full workflow data dict to store.
            notes: Optional human-readable annotation for this version.

        Returns:
            The new version number on success, None when Redis is unavailable.
        """
        redis = await get_async_redis_client(database="workflows")
        if redis is None:
            logger.error("save_version: Redis unavailable for workflow %s", workflow_id)
            return None

        version = await self._next_version(redis, workflow_id)
        created_at = _utc_now()

        record = WorkflowVersion(
            workflow_id=workflow_id,
            version=version,
            data=data,
            created_at=created_at,
            notes=notes,
        )

        payload = json.dumps(record.to_dict(), ensure_ascii=False)
        await redis.set(_version_key(workflow_id, version), payload)
        await redis.zadd(_list_key(workflow_id), {str(version): float(version)})

        logger.info(
            "Saved version %d for workflow %s (notes=%r)",
            version,
            workflow_id,
            notes,
        )
        return version

    async def delete_version(self, workflow_id: str, version: int) -> bool:
        """
        Remove version *version* from *workflow_id*'s history (#2145).

        Args:
            workflow_id: Target workflow.
            version: Version number to remove.

        Returns:
            True when the version existed and was removed; False otherwise.
        """
        redis = await get_async_redis_client(database="workflows")
        if redis is None:
            logger.error("delete_version: Redis unavailable for workflow %s", workflow_id)
            return False

        deleted = await redis.delete(_version_key(workflow_id, version))
        await redis.zrem(_list_key(workflow_id), str(version))

        if deleted:
            logger.info("Deleted version %d for workflow %s", version, workflow_id)
        else:
            logger.warning(
                "delete_version: version %d not found for workflow %s",
                version,
                workflow_id,
            )

        return bool(deleted)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_versions(self, workflow_id: str) -> List[Dict[str, Any]]:
        """
        Return version summaries for *workflow_id*, newest first (#2145).

        Each summary contains: workflow_id, version, created_at, notes.
        The full data payload is omitted to keep responses lightweight.

        Args:
            workflow_id: Target workflow.

        Returns:
            List of summary dicts sorted by version descending.  Empty list
            when no versions exist or Redis is unavailable.
        """
        redis = await get_async_redis_client(database="workflows")
        if redis is None:
            logger.error("list_versions: Redis unavailable for workflow %s", workflow_id)
            return []

        # zrevrange returns members ordered by score descending (newest version first)
        version_strs = await redis.zrevrange(_list_key(workflow_id), 0, -1)
        if not version_strs:
            return []

        summaries: List[Dict[str, Any]] = []
        for v_str in version_strs:
            raw = await redis.get(_version_key(workflow_id, int(v_str)))
            if raw is None:
                # Sorted-set entry exists but the record was deleted; skip gracefully.
                logger.warning(
                    "list_versions: record missing for workflow %s version %s",
                    workflow_id,
                    v_str,
                )
                continue
            record = json.loads(raw)
            summaries.append(_summary(record))

        return summaries

    async def get_version(self, workflow_id: str, version: int) -> WorkflowVersion | None:
        """
        Retrieve the full snapshot for *workflow_id* at *version* (#2145).

        Args:
            workflow_id: Target workflow.
            version: Specific version number to retrieve.

        Returns:
            WorkflowVersion dataclass, or None when not found.
        """
        redis = await get_async_redis_client(database="workflows")
        if redis is None:
            logger.error("get_version: Redis unavailable for workflow %s", workflow_id)
            return None

        raw = await redis.get(_version_key(workflow_id, version))
        if raw is None:
            logger.warning(
                "get_version: version %d not found for workflow %s",
                version,
                workflow_id,
            )
            return None

        return WorkflowVersion.from_dict(json.loads(raw))

    async def restore_version(self, workflow_id: str, version: int) -> Dict[str, Any] | None:
        """
        Return the data dict stored in *version* of *workflow_id* (#2145).

        The caller is responsible for applying the returned data to the live
        workflow.  This method only retrieves the snapshot; it does not modify
        any live workflow state.

        Args:
            workflow_id: Target workflow.
            version: Version number to restore from.

        Returns:
            The workflow data dict stored in that version, or None when the
            version does not exist.
        """
        wv = await self.get_version(workflow_id, version)
        if wv is None:
            return None

        logger.info("Restoring workflow %s to version %d", workflow_id, version)
        return wv.data

    async def diff_versions(
        self,
        workflow_id: str,
        v1: int,
        v2: int,
    ) -> Dict[str, Any] | None:
        """
        Compare two versions of *workflow_id* and return a diff (#2145).

        Only top-level keys of the ``steps`` list are compared.  Steps are
        matched by their ``step_id`` field; steps present in one version but
        not the other are reported as added/removed.  Steps present in both
        are compared field-by-field and reported as modified when they differ.

        Args:
            workflow_id: Target workflow.
            v1: First (older) version number.
            v2: Second (newer) version number.

        Returns:
            Dict with keys ``added``, ``removed``, ``modified`` when both
            versions exist; None when either version is missing.
        """
        wv1 = await self.get_version(workflow_id, v1)
        wv2 = await self.get_version(workflow_id, v2)

        if wv1 is None or wv2 is None:
            missing = v1 if wv1 is None else v2
            logger.warning(
                "diff_versions: version %d not found for workflow %s",
                missing,
                workflow_id,
            )
            return None

        return _diff_step_lists(wv1.data.get("steps", []), wv2.data.get("steps", []))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _next_version(redis: Any, workflow_id: str) -> int:
        """Return version = max existing version + 1, starting at 1 (#2145)."""
        members = await redis.zrevrange(_list_key(workflow_id), 0, 0)
        if not members:
            return 1
        return int(members[0]) + 1


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _summary(record: Dict[str, Any]) -> Dict[str, Any]:
    """Strip the data payload from a stored record, returning only metadata (#2145)."""
    return {
        "workflow_id": record.get("workflow_id", ""),
        "version": record.get("version"),
        "created_at": record.get("created_at", ""),
        "notes": record.get("notes", ""),
    }


def _diff_step_lists(
    steps_v1: List[Dict[str, Any]],
    steps_v2: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute added/removed/modified steps between two step lists (#2145).

    Steps are identified by their ``step_id`` field.  A step with the same
    step_id but any changed field is considered modified; the diff entry
    contains only the keys that differ.

    Args:
        steps_v1: Steps from the older version.
        steps_v2: Steps from the newer version.

    Returns:
        Dict with keys:
            added    — list of step dicts present in v2 but not v1
            removed  — list of step dicts present in v1 but not v2
            modified — list of dicts {step_id, changed_fields: {key: {from, to}}}
    """
    index_v1 = {s.get("step_id"): s for s in steps_v1 if s.get("step_id")}
    index_v2 = {s.get("step_id"): s for s in steps_v2 if s.get("step_id")}

    ids_v1 = set(index_v1)
    ids_v2 = set(index_v2)

    added = [index_v2[sid] for sid in sorted(ids_v2 - ids_v1)]
    removed = [index_v1[sid] for sid in sorted(ids_v1 - ids_v2)]

    modified: List[Dict[str, Any]] = []
    for sid in sorted(ids_v1 & ids_v2):
        changed = _changed_fields(index_v1[sid], index_v2[sid])
        if changed:
            modified.append({"step_id": sid, "changed_fields": changed})

    return {"added": added, "removed": removed, "modified": modified}


def _changed_fields(
    step_v1: Dict[str, Any],
    step_v2: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Return fields that differ between two step dicts (#2145).

    Result maps field name → {from: old_value, to: new_value}.
    """
    all_keys = set(step_v1) | set(step_v2)
    return {k: {"from": step_v1.get(k), "to": step_v2.get(k)} for k in all_keys if step_v1.get(k) != step_v2.get(k)}
