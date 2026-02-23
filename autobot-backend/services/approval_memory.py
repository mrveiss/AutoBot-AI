# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Approval Memory Manager - Redis-backed Per-Project Approval Memory

Provides persistent storage for command approvals per project directory.
When a user approves a command and checks "Remember for this project",
future identical commands will be auto-approved.

Features:
- Per-project approval memory (isolated by project path hash)
- TTL-based expiration (default 30 days)
- Pattern-based matching (remembers command patterns, not exact commands)
- Risk-level aware (only remembers approvals at same or lower risk)
- User-scoped (approvals are per-user per-project)

Usage:
    from backend.services.approval_memory import ApprovalMemoryManager

    manager = ApprovalMemoryManager()

    # Store approval
    await manager.remember_approval(
        project_path="/home/user/myproject",
        command="npm install lodash",
        user_id="user123",
        risk_level="moderate"
    )

    # Check if remembered
    if await manager.check_remembered(
        project_path="/home/user/myproject",
        command="npm install express",  # Same pattern: "npm install *"
        user_id="user123",
        risk_level="moderate"
    ):
        logger.info("Auto-approved by memory!")

    # Clear project approvals
    await manager.clear_project_approvals("/home/user/myproject")
"""

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)

# Redis key prefix for approval memory
REDIS_KEY_PREFIX = "autobot:approval_memory"


@dataclass
class ApprovalRecord:
    """A single remembered approval."""

    pattern: str  # Command pattern (e.g., "npm install *")
    tool: str  # Tool name (e.g., "Bash")
    risk_level: str  # Risk level at time of approval
    user_id: str  # User who approved
    created_at: float  # Unix timestamp
    original_command: str  # Original command that was approved
    comment: Optional[str] = None  # Optional approval comment

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalRecord":
        """Create from dictionary."""
        return cls(
            pattern=data.get("pattern", ""),
            tool=data.get("tool", "Bash"),
            risk_level=data.get("risk_level", "moderate"),
            user_id=data.get("user_id", ""),
            created_at=data.get("created_at", time.time()),
            original_command=data.get("original_command", ""),
            comment=data.get("comment"),
        )


class ApprovalMemoryManager:
    """
    Redis-backed per-project approval memory manager.

    Stores and retrieves command approval records, allowing commands
    to be auto-approved based on previous user decisions.

    The memory is organized by:
    - Project path (hashed for privacy)
    - User ID (approvals are user-specific)
    - Command pattern (glob-style patterns)

    Attributes:
        ttl: Time-to-live for approval records in seconds
        enabled: Whether approval memory is enabled
    """

    # Risk level ordering for comparison
    RISK_LEVELS = {
        "safe": 0,
        "moderate": 1,
        "high": 2,
        "critical": 3,
        "forbidden": 4,
    }

    def __init__(
        self,
        ttl: Optional[int] = None,
        enabled: Optional[bool] = None,
    ):
        """
        Initialize approval memory manager.

        Args:
            ttl: Time-to-live for records in seconds. Uses config default if not provided.
            enabled: Whether memory is enabled. Uses config default if not provided.
        """
        self.ttl = ttl or config.permission.approval_memory_ttl
        self.enabled = (
            enabled
            if enabled is not None
            else config.permission.approval_memory_enabled
        )

        if self.enabled:
            logger.info(
                f"ApprovalMemoryManager initialized: ttl={self.ttl}s "
                f"({self.ttl // 86400} days)"
            )
        else:
            logger.info("ApprovalMemoryManager disabled by configuration")

    def _get_project_hash(self, project_path: str) -> str:
        """
        Generate a hash for the project path.

        Args:
            project_path: Full path to project directory

        Returns:
            SHA256 hash of the normalized path
        """
        # Normalize path (remove trailing slashes, resolve relative paths)
        normalized = project_path.rstrip("/").lower()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _get_redis_key(self, project_path: str, user_id: str) -> str:
        """
        Generate Redis key for project+user combination.

        Args:
            project_path: Project directory path
            user_id: User identifier

        Returns:
            Redis key string
        """
        project_hash = self._get_project_hash(project_path)
        return f"{REDIS_KEY_PREFIX}:{project_hash}:{user_id}"

    def _extract_pattern(self, command: str, tool: str = "Bash") -> str:
        """
        Extract a pattern from a command for matching.

        Examples:
            "npm install lodash" -> "npm install *"
            "git commit -m 'message'" -> "git commit *"
            "ls -la" -> "ls *"
            "pwd" -> "pwd"

        Args:
            command: Full command string
            tool: Tool name (for tool-specific patterns)

        Returns:
            Pattern string for matching
        """
        parts = command.split()
        if len(parts) == 0:
            return command

        base_cmd = parts[0]

        # Commands with subcommands that should be preserved
        subcommand_tools = {"git", "docker", "kubectl", "npm", "yarn", "pip"}

        if len(parts) > 1:
            # For commands with subcommands, preserve the subcommand
            if base_cmd in subcommand_tools and len(parts) >= 2:
                return f"{base_cmd} {parts[1]} *"
            # For other commands, just preserve the base command
            return f"{base_cmd} *"

        # No arguments - exact match
        return base_cmd

    async def _load_existing_records(self, redis, key: str) -> List[Dict]:
        """
        Load existing approval records from Redis.

        Issue #665: Extracted from remember_approval to reduce function length.

        Args:
            redis: Redis client
            key: Redis key for records

        Returns:
            List of existing records or empty list
        """
        existing_data = await redis.get(key)
        if existing_data:
            try:
                return json.loads(existing_data)
            except json.JSONDecodeError:
                return []
        return []

    def _update_or_add_record(
        self, records: List[Dict], record: ApprovalRecord, pattern: str, tool: str
    ) -> List[Dict]:
        """
        Update existing record or add new one.

        Issue #665: Extracted from remember_approval to reduce function length.

        Args:
            records: Existing records list
            record: New record to add/update
            pattern: Pattern to match
            tool: Tool to match

        Returns:
            Updated records list
        """
        for i, rec in enumerate(records):
            if rec.get("pattern") == pattern and rec.get("tool") == tool:
                records[i] = record.to_dict()
                return records
        records.append(record.to_dict())
        return records

    async def remember_approval(
        self,
        project_path: str,
        command: str,
        user_id: str,
        risk_level: str,
        tool: str = "Bash",
        comment: Optional[str] = None,
    ) -> bool:
        """
        Store an approval for future auto-approval.

        Args:
            project_path: Project directory path
            command: Command that was approved
            user_id: User who approved
            risk_level: Risk level of the command
            tool: Tool name (default: "Bash")
            comment: Optional approval comment

        Returns:
            True if stored successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Approval memory disabled, skipping store")
            return False

        try:
            redis = get_redis_client(async_client=True, database="main")
            if not redis:
                logger.warning("Redis not available for approval memory")
                return False

            # Create approval record
            pattern = self._extract_pattern(command, tool)
            record = ApprovalRecord(
                pattern=pattern,
                tool=tool,
                risk_level=risk_level.lower(),
                user_id=user_id,
                created_at=time.time(),
                original_command=command,
                comment=comment,
            )

            # Get Redis key
            key = self._get_redis_key(project_path, user_id)

            # Get existing records and update (Issue #665: uses helper)
            records = await self._load_existing_records(redis, key)
            records = self._update_or_add_record(records, record, pattern, tool)

            # Store with TTL
            await redis.setex(key, self.ttl, json.dumps(records))

            logger.info(
                f"Approval stored: user={user_id}, project_hash={self._get_project_hash(project_path)}, "
                f"pattern='{pattern}', risk={risk_level}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store approval: {e}")
            return False

    async def check_remembered(
        self,
        project_path: str,
        command: str,
        user_id: str,
        risk_level: str,
        tool: str = "Bash",
    ) -> bool:
        """Check if a command should be auto-approved based on memory. Ref: #1088."""
        if not self.enabled:
            return False

        try:
            redis = get_redis_client(async_client=True, database="main")
            if not redis:
                return False

            # Get Redis key
            key = self._get_redis_key(project_path, user_id)

            # Get stored records
            data = await redis.get(key)
            if not data:
                return False

            try:
                records = json.loads(data)
            except json.JSONDecodeError:
                return False

            # Extract pattern from current command
            pattern = self._extract_pattern(command, tool)
            current_risk = self.RISK_LEVELS.get(risk_level.lower(), 999)

            # Check for matching approval
            for rec in records:
                if rec.get("pattern") == pattern and rec.get("tool") == tool:
                    # Check risk level - only approve if at same or lower risk
                    stored_risk = self.RISK_LEVELS.get(rec.get("risk_level", ""), 0)
                    if current_risk <= stored_risk:
                        logger.info(
                            f"Auto-approved by memory: pattern='{pattern}', "
                            f"user={user_id}, stored_risk={rec.get('risk_level')}, "
                            f"current_risk={risk_level}"
                        )
                        return True
                    else:
                        logger.debug(
                            f"Memory exists but risk level increased: "
                            f"{rec.get('risk_level')} -> {risk_level}"
                        )

            return False

        except Exception as e:
            logger.error(f"Failed to check approval memory: {e}")
            return False

    async def get_project_approvals(
        self, project_path: str, user_id: str
    ) -> List[ApprovalRecord]:
        """
        Get all stored approvals for a project.

        Args:
            project_path: Project directory path
            user_id: User identifier

        Returns:
            List of approval records
        """
        if not self.enabled:
            return []

        try:
            redis = get_redis_client(async_client=True, database="main")
            if not redis:
                return []

            key = self._get_redis_key(project_path, user_id)
            data = await redis.get(key)

            if not data:
                return []

            try:
                records = json.loads(data)
                return [ApprovalRecord.from_dict(r) for r in records]
            except json.JSONDecodeError:
                return []

        except Exception as e:
            logger.error(f"Failed to get project approvals: {e}")
            return []

    async def clear_project_approvals(
        self, project_path: str, user_id: Optional[str] = None
    ) -> bool:
        """
        Clear approval memory for a project.

        Args:
            project_path: Project directory path
            user_id: If provided, only clear for this user.
                    If None, clear for all users (requires scanning).

        Returns:
            True if cleared successfully
        """
        if not self.enabled:
            return False

        try:
            redis = get_redis_client(async_client=True, database="main")
            if not redis:
                return False

            if user_id:
                # Clear specific user's approvals
                key = self._get_redis_key(project_path, user_id)
                await redis.delete(key)
                logger.info(
                    f"Cleared approvals: project_hash={self._get_project_hash(project_path)}, "
                    f"user={user_id}"
                )
            else:
                # Clear all users' approvals for this project
                # This requires scanning keys with the project hash
                project_hash = self._get_project_hash(project_path)
                pattern = f"{REDIS_KEY_PREFIX}:{project_hash}:*"

                cursor = 0
                deleted = 0
                while True:
                    cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await redis.delete(*keys)
                        deleted += len(keys)
                    if cursor == 0:
                        break

                logger.info(
                    f"Cleared all approvals for project: "
                    f"project_hash={project_hash}, deleted={deleted} records"
                )

            return True

        except Exception as e:
            logger.error(f"Failed to clear project approvals: {e}")
            return False

    async def remove_approval(
        self,
        project_path: str,
        user_id: str,
        pattern: str,
        tool: str = "Bash",
    ) -> bool:
        """Remove a specific approval record. Ref: #1088."""
        if not self.enabled:
            return False

        try:
            redis = get_redis_client(async_client=True, database="main")
            if not redis:
                return False

            key = self._get_redis_key(project_path, user_id)
            data = await redis.get(key)

            if not data:
                return False

            try:
                records = json.loads(data)
            except json.JSONDecodeError:
                return False

            # Find and remove matching record
            original_count = len(records)
            records = [
                r
                for r in records
                if not (r.get("pattern") == pattern and r.get("tool") == tool)
            ]

            if len(records) == original_count:
                return False  # Not found

            if records:
                # Update with remaining records
                ttl = await redis.ttl(key)
                if ttl > 0:
                    await redis.setex(key, ttl, json.dumps(records))
                else:
                    await redis.setex(key, self.ttl, json.dumps(records))
            else:
                # No records left, delete key
                await redis.delete(key)

            logger.info(f"Removed approval: pattern='{pattern}', user={user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove approval: {e}")
            return False

    async def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get statistics about approval memory.

        Returns:
            Dictionary with memory statistics
        """
        if not self.enabled:
            return {"enabled": False}

        try:
            redis = get_redis_client(async_client=True, database="main")
            if not redis:
                return {"enabled": True, "redis_available": False}

            # Count total keys
            pattern = f"{REDIS_KEY_PREFIX}:*"
            cursor = 0
            total_keys = 0

            while True:
                cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                total_keys += len(keys)
                if cursor == 0:
                    break

            return {
                "enabled": True,
                "redis_available": True,
                "total_project_user_combinations": total_keys,
                "ttl_seconds": self.ttl,
                "ttl_days": self.ttl // 86400,
            }

        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"enabled": True, "error": str(e)}


# Singleton instance for easy access
_memory_instance: Optional[ApprovalMemoryManager] = None


def get_approval_memory() -> ApprovalMemoryManager:
    """
    Get or create the global approval memory manager instance.

    Returns:
        ApprovalMemoryManager instance
    """
    global _memory_instance

    if _memory_instance is None:
        _memory_instance = ApprovalMemoryManager()

    return _memory_instance
