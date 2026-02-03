# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Checkpoint Manager for Long-Running Operations

Issue #381: Extracted from long_running_operations_framework.py god class refactoring.
Handles checkpoint save/load/resume functionality.
"""

import json
import logging
import pickle
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiofiles
import redis.asyncio as redis

from src.constants.path_constants import PATH

from .types import OperationCheckpoint

logger = logging.getLogger(__name__)


class OperationCheckpointManager:
    """Manages operation checkpoints for pause/resume capability."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize checkpoint manager with optional Redis client."""
        self.redis_client = redis_client
        self.checkpoint_dir = PATH.PROJECT_ROOT / "data" / "operation_checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    async def save_checkpoint(
        self,
        operation_id: str,
        checkpoint_id: str,
        progress_percent: float,
        state_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OperationCheckpoint:
        """
        Save a checkpoint for an operation.

        Args:
            operation_id: The operation ID
            checkpoint_id: Unique checkpoint identifier
            progress_percent: Current progress percentage
            state_data: Serializable state data for resume
            metadata: Optional metadata about the checkpoint

        Returns:
            The created checkpoint
        """
        checkpoint = OperationCheckpoint(
            checkpoint_id=checkpoint_id,
            operation_id=operation_id,
            checkpoint_time=datetime.now(),
            progress_percent=progress_percent,
            state_data=state_data,
            metadata=metadata or {},
        )

        # Save to file (primary storage)
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"
        checkpoint_data = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "operation_id": checkpoint.operation_id,
            "checkpoint_time": checkpoint.checkpoint_time.isoformat(),
            "progress_percent": checkpoint.progress_percent,
            "state_data": checkpoint.state_data,
            "metadata": checkpoint.metadata,
        }

        async with aiofiles.open(checkpoint_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(checkpoint_data, indent=2))

        # Also save to Redis for fast lookup if available
        if self.redis_client:
            try:
                redis_key = f"checkpoint:{operation_id}:{checkpoint_id}"
                await self.redis_client.hset(
                    redis_key,
                    mapping={
                        "data": pickle.dumps(checkpoint_data),
                        "progress": str(progress_percent),
                        "timestamp": checkpoint.checkpoint_time.isoformat(),
                    },
                )
                await self.redis_client.expire(redis_key, 86400 * 7)  # 7 days TTL
            except Exception as e:
                logger.warning("Failed to save checkpoint to Redis: %s", e)

        logger.info(
            "Checkpoint saved: %s at %.1f%%",
            checkpoint_id,
            progress_percent,
        )

        return checkpoint

    async def load_checkpoint(
        self, checkpoint_id: str
    ) -> Optional[OperationCheckpoint]:
        """
        Load a checkpoint by ID.

        Args:
            checkpoint_id: The checkpoint ID to load

        Returns:
            The checkpoint or None if not found
        """
        # Try Redis first for speed
        if self.redis_client:
            try:
                # Find the operation ID first
                keys = await self.redis_client.keys(f"checkpoint:*:{checkpoint_id}")
                if keys:
                    redis_key = keys[0]
                    data = await self.redis_client.hget(redis_key, "data")
                    if data:
                        checkpoint_data = pickle.loads(data)
                        return OperationCheckpoint(
                            checkpoint_id=checkpoint_data["checkpoint_id"],
                            operation_id=checkpoint_data["operation_id"],
                            checkpoint_time=datetime.fromisoformat(
                                checkpoint_data["checkpoint_time"]
                            ),
                            progress_percent=checkpoint_data["progress_percent"],
                            state_data=checkpoint_data["state_data"],
                            metadata=checkpoint_data.get("metadata", {}),
                        )
            except Exception as e:
                logger.warning("Failed to load checkpoint from Redis: %s", e)

        # Fall back to file storage
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"
        if checkpoint_file.exists():
            async with aiofiles.open(checkpoint_file, "r", encoding="utf-8") as f:
                checkpoint_data = json.loads(await f.read())
                return OperationCheckpoint(
                    checkpoint_id=checkpoint_data["checkpoint_id"],
                    operation_id=checkpoint_data["operation_id"],
                    checkpoint_time=datetime.fromisoformat(
                        checkpoint_data["checkpoint_time"]
                    ),
                    progress_percent=checkpoint_data["progress_percent"],
                    state_data=checkpoint_data["state_data"],
                    metadata=checkpoint_data.get("metadata", {}),
                )

        return None

    async def list_checkpoints(
        self, operation_id: str
    ) -> List[OperationCheckpoint]:
        """
        List all checkpoints for an operation.

        Args:
            operation_id: The operation ID

        Returns:
            List of checkpoints sorted by time
        """
        checkpoints = []

        # Check Redis first
        if self.redis_client:
            try:
                keys = await self.redis_client.keys(f"checkpoint:{operation_id}:*")
                # Issue #397: Fix N+1 query pattern - use pipeline for batch retrieval
                if keys:
                    pipe = self.redis_client.pipeline()
                    for key in keys:
                        pipe.hget(key, "data")
                    results = await pipe.execute()

                    for data in results:
                        if data:
                            checkpoint_data = pickle.loads(data)
                            checkpoints.append(
                                OperationCheckpoint(
                                    checkpoint_id=checkpoint_data["checkpoint_id"],
                                    operation_id=checkpoint_data["operation_id"],
                                    checkpoint_time=datetime.fromisoformat(
                                        checkpoint_data["checkpoint_time"]
                                    ),
                                    progress_percent=checkpoint_data["progress_percent"],
                                    state_data=checkpoint_data["state_data"],
                                    metadata=checkpoint_data.get("metadata", {}),
                                )
                            )
            except Exception as e:
                logger.warning("Failed to list checkpoints from Redis: %s", e)

        # Also check file storage
        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            try:
                async with aiofiles.open(
                    checkpoint_file, "r", encoding="utf-8"
                ) as f:
                    checkpoint_data = json.loads(await f.read())
                    if checkpoint_data.get("operation_id") == operation_id:
                        checkpoint = OperationCheckpoint(
                            checkpoint_id=checkpoint_data["checkpoint_id"],
                            operation_id=checkpoint_data["operation_id"],
                            checkpoint_time=datetime.fromisoformat(
                                checkpoint_data["checkpoint_time"]
                            ),
                            progress_percent=checkpoint_data["progress_percent"],
                            state_data=checkpoint_data["state_data"],
                            metadata=checkpoint_data.get("metadata", {}),
                        )
                        # Avoid duplicates
                        if not any(
                            c.checkpoint_id == checkpoint.checkpoint_id
                            for c in checkpoints
                        ):
                            checkpoints.append(checkpoint)
            except Exception as e:
                logger.warning(
                    "Failed to read checkpoint file %s: %s",
                    checkpoint_file,
                    e,
                )

        # Sort by checkpoint time
        checkpoints.sort(key=lambda x: x.checkpoint_time)
        return checkpoints

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Delete a checkpoint.

        Args:
            checkpoint_id: The checkpoint ID to delete

        Returns:
            True if deleted, False otherwise
        """
        deleted = False

        # Delete from Redis
        if self.redis_client:
            try:
                keys = await self.redis_client.keys(f"checkpoint:*:{checkpoint_id}")
                # Issue #397: Fix N+1 pattern - batch delete using unpack
                if keys:
                    await self.redis_client.delete(*keys)
                    deleted = True
            except Exception as e:
                logger.warning("Failed to delete checkpoint from Redis: %s", e)

        # Delete from file storage
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            deleted = True

        return deleted

    async def get_latest_checkpoint(
        self, operation_id: str
    ) -> Optional[OperationCheckpoint]:
        """
        Get the most recent checkpoint for an operation.

        Args:
            operation_id: The operation ID

        Returns:
            The latest checkpoint or None
        """
        checkpoints = await self.list_checkpoints(operation_id)
        return checkpoints[-1] if checkpoints else None
