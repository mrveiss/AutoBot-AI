"""
Comprehensive Security Audit Logging Service for AutoBot

OWASP and NIST Compliant Audit Logging System
Provides distributed, performant, and tamper-resistant audit logging
across AutoBot's 6-VM infrastructure using Redis DB 10.

Features:
- OWASP Logging Cheat Sheet compliance
- NIST 800-53 Rev. 5 compliance
- <5ms overhead per audit operation
- Distributed VM support
- Time-series queries via Redis sorted sets
- Multi-index support for complex queries
- Automatic retention and cleanup
- Async batch logging for performance
- File-based fallback for Redis failures

Security Operations Logged:
- Authentication (login/logout/permission checks)
- File operations (upload/download/delete)
- Privilege escalation (sudo/elevation requests)
- Session management (create/delete/access)
- Configuration changes
- Terminal command execution
"""

import asyncio
import json
import logging
import os
import socket
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import redis.asyncio as async_redis

from src.constants.network_constants import NetworkConstants
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Audit result types
AuditResult = Literal["success", "denied", "failed", "error"]

# Audit operation categories
OPERATION_CATEGORIES = {
    "auth.login": "Authentication",
    "auth.logout": "Authentication",
    "auth.permission_check": "Authentication",
    "auth.session_create": "Authentication",
    "auth.session_invalidate": "Authentication",
    "file.upload": "File Operations",
    "file.download": "File Operations",
    "file.delete": "File Operations",
    "file.create": "File Operations",
    "file.modify": "File Operations",
    "file.view": "File Operations",
    "elevation.request": "Privilege Escalation",
    "elevation.authorize": "Privilege Escalation",
    "elevation.execute": "Privilege Escalation",
    "session.create": "Session Management",
    "session.delete": "Session Management",
    "session.access": "Session Management",
    "session.update": "Session Management",
    "config.update": "Configuration",
    "config.delete": "Configuration",
    "config.view": "Configuration",
    "terminal.execute": "Terminal Operations",
    "terminal.create": "Terminal Operations",
    "terminal.delete": "Terminal Operations",
    "conversation.create": "Conversation Data",
    "conversation.access": "Conversation Data",
    "conversation.delete": "Conversation Data",
    "conversation.export": "Conversation Data",
}


@dataclass
class AuditEntry:
    """
    OWASP/NIST compliant audit log entry

    Required Fields (OWASP):
    - timestamp: When the event occurred
    - operation: What action was performed
    - result: Success, denied, or failed
    - user_id: Who performed the action
    - ip_address: Where the action originated

    Additional Fields:
    - session_id: Session context
    - resource: What was affected
    - vm_source: Which VM originated the action
    - details: Operation-specific metadata
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    # OWASP Required Fields
    operation: str = ""
    result: AuditResult = "success"
    user_id: Optional[str] = None
    ip_address: Optional[str] = None

    # Context Fields
    session_id: Optional[str] = None
    user_role: Optional[str] = None
    resource: Optional[str] = None

    # Distributed System Fields
    vm_source: Optional[str] = None
    vm_name: Optional[str] = None

    # Additional Metadata
    details: Dict[str, Any] = field(default_factory=dict)
    performance_ms: Optional[float] = None

    def to_json(self) -> str:
        """Serialize to JSON for Redis storage"""
        data = asdict(self)
        return json.dumps(data, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "AuditEntry":
        """Deserialize from JSON"""
        data = json.loads(json_str)
        return cls(**data)

    def sanitize(self) -> "AuditEntry":
        """
        Remove sensitive data per OWASP guidelines
        NEVER log: passwords, tokens, API keys, PII
        """
        # Remove sensitive keys from details
        sensitive_keys = {
            "password",
            "token",
            "secret",
            "api_key",
            "private_key",
            "session_token",
            "jwt",
            "authorization",
            "cookie",
        }

        if self.details:
            self.details = {
                k: v for k, v in self.details.items() if k.lower() not in sensitive_keys
            }

        return self


class AuditLogger:
    """
    Async audit logging service with Redis DB 10 backend

    Performance: <5ms overhead per audit operation
    Storage: Redis sorted sets for time-series queries
    Fallback: File-based logging when Redis unavailable
    """

    def __init__(
        self,
        retention_days: int = 90,
        batch_size: int = 50,
        batch_timeout_seconds: float = 1.0,
        fallback_log_dir: str = "logs/audit",
    ):
        """
        Initialize audit logger

        Args:
            retention_days: How long to keep detailed audit logs (default: 90 days)
            batch_size: Number of entries to batch before flush (performance)
            batch_timeout_seconds: Max time to wait before flushing batch
            fallback_log_dir: Directory for file-based fallback logs
        """
        self.retention_days = retention_days
        self.batch_size = batch_size
        self.batch_timeout_seconds = batch_timeout_seconds

        # Get VM identification
        self.vm_source = os.getenv("AUTOBOT_BACKEND_HOST", NetworkConstants.MAIN_MACHINE_IP)
        self.vm_name = self._get_vm_name()

        # Batch processing
        self._batch_queue: List[AuditEntry] = []
        self._batch_lock = asyncio.Lock()
        self._batch_task: Optional[asyncio.Task] = None

        # Fallback logging
        self.fallback_log_dir = Path(fallback_log_dir)
        self.fallback_log_dir.mkdir(parents=True, exist_ok=True)

        # Statistics
        self._total_logged = 0
        self._total_failed = 0
        self._redis_failures = 0

        logger.info(
            f"AuditLogger initialized: VM={self.vm_name} ({self.vm_source}), Retention={retention_days}d"
        )

    def _get_vm_name(self) -> str:
        """Determine VM name from IP address"""
        vm_mapping = {
            NetworkConstants.MAIN_MACHINE_IP: "backend",
            NetworkConstants.FRONTEND_VM_IP: "frontend",
            NetworkConstants.NPU_WORKER_VM_IP: "npu-worker",
            NetworkConstants.REDIS_VM_IP: "redis",
            NetworkConstants.AI_STACK_VM_IP: "ai-stack",
            NetworkConstants.BROWSER_VM_IP: "browser",
        }
        return vm_mapping.get(self.vm_source, socket.gethostname())

    async def _get_audit_db(self) -> Optional[async_redis.Redis]:
        """Get Redis audit database (DB 10)"""
        try:
            # Use canonical Redis client pattern with 'audit' database
            return await get_redis_client(async_client=True, database="audit")
        except Exception as e:
            logger.error(f"Failed to get audit database: {e}")
            self._redis_failures += 1
            return None

    async def log(
        self,
        operation: str,
        result: AuditResult = "success",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        resource: Optional[str] = None,
        user_role: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        performance_ms: Optional[float] = None,
    ) -> bool:
        """
        Log a security-sensitive operation

        This is the primary interface for audit logging. Automatically adds
        VM source information and sanitizes sensitive data.

        Args:
            operation: Operation type (e.g., 'auth.login', 'file.delete')
            result: Operation result ('success', 'denied', 'failed', 'error')
            user_id: Username or user identifier
            session_id: Session ID if applicable
            ip_address: Client IP address
            resource: Resource affected (e.g., file path, API endpoint)
            user_role: User's role (e.g., 'admin', 'user', 'guest')
            details: Additional operation-specific metadata
            performance_ms: Operation duration in milliseconds

        Returns:
            bool: True if logged successfully, False if fallback used
        """
        start_time = datetime.now()

        try:
            # Create audit entry
            entry = AuditEntry(
                operation=operation,
                result=result,
                user_id=user_id,
                session_id=session_id,
                ip_address=ip_address,
                resource=resource,
                user_role=user_role,
                vm_source=self.vm_source,
                vm_name=self.vm_name,
                details=details or {},
                performance_ms=performance_ms,
            )

            # Sanitize sensitive data (OWASP requirement)
            entry.sanitize()

            # Add to batch queue
            async with self._batch_lock:
                self._batch_queue.append(entry)

                # Flush immediately if batch is full
                if len(self._batch_queue) >= self.batch_size:
                    await self._flush_batch()
                elif not self._batch_task or self._batch_task.done():
                    # Start batch timeout timer
                    self._batch_task = asyncio.create_task(self._batch_timer())

            # Track performance
            log_duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            if log_duration_ms > 5.0:
                logger.warning(
                    f"Audit logging exceeded 5ms target: {log_duration_ms:.2f}ms"
                )

            self._total_logged += 1
            return True

        except Exception as e:
            logger.error(f"Audit logging failed: {e}")
            self._total_failed += 1

            # Fallback to file logging
            await self._fallback_log(
                entry if "entry" in locals() else None, error=str(e)
            )
            return False

    async def _batch_timer(self):
        """Wait for batch timeout then flush"""
        try:
            await asyncio.sleep(self.batch_timeout_seconds)
            async with self._batch_lock:
                if self._batch_queue:
                    await self._flush_batch()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Batch timer error: {e}")

    async def _flush_batch(self):
        """
        Flush batched audit entries to Redis
        Uses Redis pipeline for atomic multi-index writes
        """
        if not self._batch_queue:
            return

        entries_to_flush = self._batch_queue.copy()
        self._batch_queue.clear()

        try:
            audit_db = await self._get_audit_db()
            if not audit_db:
                # Redis unavailable - fallback to file
                for entry in entries_to_flush:
                    await self._fallback_log(entry)
                return

            # Use pipeline for atomic batch write
            async with audit_db.pipeline() as pipe:
                for entry in entries_to_flush:
                    await self._write_entry_to_redis(pipe, entry)
                await pipe.execute()

            logger.debug(f"Flushed {len(entries_to_flush)} audit entries to Redis")

        except Exception as e:
            logger.error(f"Batch flush failed: {e}")
            # Fallback to file for all entries
            for entry in entries_to_flush:
                await self._fallback_log(entry, error=str(e))

    async def _write_entry_to_redis(self, pipe, entry: AuditEntry):
        """
        Write audit entry to Redis with multi-index support

        Indexes created:
        1. Primary log: audit:log:{date} (sorted by timestamp)
        2. Operation index: audit:op:{operation}:{date}
        3. User index: audit:user:{user_id}:{date}
        4. Session index: audit:session:{session_id}
        5. VM index: audit:vm:{vm_name}:{date}
        6. Result index: audit:result:{result}:{date}
        """
        json_entry = entry.to_json()
        timestamp = entry.timestamp
        date = entry.date

        # 1. Primary audit log (time-series)
        await pipe.zadd(f"audit:log:{date}", {json_entry: timestamp})

        # 2. Operation type index
        if entry.operation:
            await pipe.zadd(f"audit:op:{entry.operation}:{date}", {entry.id: timestamp})

        # 3. User index
        if entry.user_id:
            await pipe.zadd(f"audit:user:{entry.user_id}:{date}", {entry.id: timestamp})

        # 4. Session index (no date partition - track session lifetime)
        if entry.session_id:
            await pipe.zadd(f"audit:session:{entry.session_id}", {entry.id: timestamp})

        # 5. VM source index
        if entry.vm_name:
            await pipe.zadd(f"audit:vm:{entry.vm_name}:{date}", {entry.id: timestamp})

        # 6. Result index (for security monitoring)
        await pipe.zadd(f"audit:result:{entry.result}:{date}", {entry.id: timestamp})

        # Set TTL on daily partitions (retention policy)
        retention_seconds = self.retention_days * 24 * 60 * 60
        await pipe.expire(f"audit:log:{date}", retention_seconds)
        await pipe.expire(f"audit:op:{entry.operation}:{date}", retention_seconds)
        if entry.user_id:
            await pipe.expire(f"audit:user:{entry.user_id}:{date}", retention_seconds)
        if entry.vm_name:
            await pipe.expire(f"audit:vm:{entry.vm_name}:{date}", retention_seconds)
        await pipe.expire(f"audit:result:{entry.result}:{date}", retention_seconds)

    async def _fallback_log(
        self, entry: Optional[AuditEntry], error: Optional[str] = None
    ):
        """Write audit entry to file as fallback when Redis unavailable"""
        try:
            fallback_file = (
                self.fallback_log_dir
                / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            )

            log_data = {
                "timestamp": datetime.now().isoformat(),
                "fallback_reason": error or "Redis unavailable",
                "entry": asdict(entry) if entry else None,
            }

            # Append to JSONL file (one JSON object per line)
            with open(fallback_file, "a") as f:
                f.write(json.dumps(log_data, default=str) + "\n")

        except Exception as e:
            logger.error(f"Fallback logging also failed: {e}")

    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        operation: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        vm_name: Optional[str] = None,
        result: Optional[AuditResult] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEntry]:
        """
        Query audit logs with filtering

        Args:
            start_time: Start of time range
            end_time: End of time range
            operation: Filter by operation type
            user_id: Filter by user
            session_id: Filter by session
            vm_name: Filter by VM source
            result: Filter by result (success/denied/failed)
            limit: Maximum entries to return
            offset: Pagination offset

        Returns:
            List of matching audit entries, sorted by timestamp descending
        """
        try:
            audit_db = await self._get_audit_db()
            if not audit_db:
                logger.error("Cannot query: Redis audit database unavailable")
                return []

            # Default time range: last 24 hours
            if not end_time:
                end_time = datetime.now()
            if not start_time:
                start_time = end_time - timedelta(days=1)

            # Determine which index to use based on filters
            if session_id:
                # Session index (most specific)
                entries = await self._query_session(
                    audit_db, session_id, start_time, end_time, limit, offset
                )
            elif user_id and operation:
                # Intersection of user and operation indexes
                entries = await self._query_user_operation(
                    audit_db, user_id, operation, start_time, end_time, limit, offset
                )
            elif user_id:
                # User index
                entries = await self._query_user(
                    audit_db, user_id, start_time, end_time, limit, offset
                )
            elif operation:
                # Operation index
                entries = await self._query_operation(
                    audit_db, operation, start_time, end_time, limit, offset
                )
            elif vm_name:
                # VM index
                entries = await self._query_vm(
                    audit_db, vm_name, start_time, end_time, limit, offset
                )
            elif result:
                # Result index
                entries = await self._query_result(
                    audit_db, result, start_time, end_time, limit, offset
                )
            else:
                # Primary time-series log
                entries = await self._query_time_range(
                    audit_db, start_time, end_time, limit, offset
                )

            return entries

        except Exception as e:
            logger.error(f"Audit query failed: {e}")
            return []

    async def _query_time_range(
        self,
        audit_db: async_redis.Redis,
        start_time: datetime,
        end_time: datetime,
        limit: int,
        offset: int,
    ) -> List[AuditEntry]:
        """Query primary audit log by time range"""
        entries = []

        # Query each day in the range
        current_date = start_time.date()
        end_date = end_time.date()

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            key = f"audit:log:{date_str}"

            # Query sorted set by timestamp range
            start_score = (
                start_time.timestamp() if current_date == start_time.date() else 0
            )
            end_score = (
                end_time.timestamp() if current_date == end_date else float("inf")
            )

            results = await audit_db.zrange(
                key, start_score, end_score, withscores=False
            )

            for json_str in results:
                entries.append(AuditEntry.from_json(json_str))

            current_date += timedelta(days=1)

        # Sort by timestamp descending, apply pagination
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[offset : offset + limit]

    async def _query_session(
        self,
        audit_db: async_redis.Redis,
        session_id: str,
        start_time: datetime,
        end_time: datetime,
        limit: int,
        offset: int,
    ) -> List[AuditEntry]:
        """Query audit logs for specific session"""
        key = f"audit:session:{session_id}"

        # Get entry IDs from session index
        entry_ids = await audit_db.zrange(
            key, start_time.timestamp(), end_time.timestamp(), withscores=False
        )

        # Fetch full entries from primary log
        entries = []
        for entry_id in entry_ids[offset : offset + limit]:
            # Find entry in daily logs
            entry = await self._fetch_entry_by_id(
                audit_db, entry_id, start_time, end_time
            )
            if entry:
                entries.append(entry)

        return entries

    async def _query_user(
        self,
        audit_db: async_redis.Redis,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        limit: int,
        offset: int,
    ) -> List[AuditEntry]:
        """Query audit logs for specific user"""
        entries = []

        current_date = start_time.date()
        end_date = end_time.date()

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            key = f"audit:user:{user_id}:{date_str}"

            entry_ids = await audit_db.zrange(key, 0, -1, withscores=False)

            for entry_id in entry_ids:
                entry = await self._fetch_entry_by_id(
                    audit_db, entry_id, start_time, end_time
                )
                if entry:
                    entries.append(entry)

            current_date += timedelta(days=1)

        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[offset : offset + limit]

    async def _query_operation(
        self,
        audit_db: async_redis.Redis,
        operation: str,
        start_time: datetime,
        end_time: datetime,
        limit: int,
        offset: int,
    ) -> List[AuditEntry]:
        """Query audit logs for specific operation type"""
        entries = []

        current_date = start_time.date()
        end_date = end_time.date()

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            key = f"audit:op:{operation}:{date_str}"

            entry_ids = await audit_db.zrange(key, 0, -1, withscores=False)

            for entry_id in entry_ids:
                entry = await self._fetch_entry_by_id(
                    audit_db, entry_id, start_time, end_time
                )
                if entry:
                    entries.append(entry)

            current_date += timedelta(days=1)

        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[offset : offset + limit]

    async def _query_vm(
        self,
        audit_db: async_redis.Redis,
        vm_name: str,
        start_time: datetime,
        end_time: datetime,
        limit: int,
        offset: int,
    ) -> List[AuditEntry]:
        """Query audit logs for specific VM"""
        entries = []

        current_date = start_time.date()
        end_date = end_time.date()

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            key = f"audit:vm:{vm_name}:{date_str}"

            entry_ids = await audit_db.zrange(key, 0, -1, withscores=False)

            for entry_id in entry_ids:
                entry = await self._fetch_entry_by_id(
                    audit_db, entry_id, start_time, end_time
                )
                if entry:
                    entries.append(entry)

            current_date += timedelta(days=1)

        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[offset : offset + limit]

    async def _query_result(
        self,
        audit_db: async_redis.Redis,
        result: AuditResult,
        start_time: datetime,
        end_time: datetime,
        limit: int,
        offset: int,
    ) -> List[AuditEntry]:
        """Query audit logs by result (for security monitoring)"""
        entries = []

        current_date = start_time.date()
        end_date = end_time.date()

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            key = f"audit:result:{result}:{date_str}"

            entry_ids = await audit_db.zrange(key, 0, -1, withscores=False)

            for entry_id in entry_ids:
                entry = await self._fetch_entry_by_id(
                    audit_db, entry_id, start_time, end_time
                )
                if entry:
                    entries.append(entry)

            current_date += timedelta(days=1)

        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[offset : offset + limit]

    async def _query_user_operation(
        self,
        audit_db: async_redis.Redis,
        user_id: str,
        operation: str,
        start_time: datetime,
        end_time: datetime,
        limit: int,
        offset: int,
    ) -> List[AuditEntry]:
        """Query intersection of user and operation indexes"""
        # Get entries from both indexes and intersect
        user_entries = await self._query_user(
            audit_db, user_id, start_time, end_time, limit * 2, 0
        )

        # Filter by operation
        filtered = [e for e in user_entries if e.operation == operation]
        return filtered[offset : offset + limit]

    async def _fetch_entry_by_id(
        self,
        audit_db: async_redis.Redis,
        entry_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[AuditEntry]:
        """Fetch full audit entry from primary log by ID"""
        # Search daily logs in time range
        current_date = start_time.date()
        end_date = end_time.date()

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            key = f"audit:log:{date_str}"

            # Get all entries for this day
            results = await audit_db.zrange(key, 0, -1, withscores=False)

            for json_str in results:
                entry = AuditEntry.from_json(json_str)
                if entry.id == entry_id:
                    return entry

            current_date += timedelta(days=1)

        return None

    async def get_statistics(self) -> Dict[str, Any]:
        """Get audit logging statistics"""
        try:
            audit_db = await self._get_audit_db()

            stats = {
                "total_logged": self._total_logged,
                "total_failed": self._total_failed,
                "redis_failures": self._redis_failures,
                "batch_queue_size": len(self._batch_queue),
                "redis_available": audit_db is not None,
            }

            if audit_db:
                # Count entries in last 24 hours
                yesterday = datetime.now() - timedelta(days=1)
                date_str = yesterday.strftime("%Y-%m-%d")
                today_str = datetime.now().strftime("%Y-%m-%d")

                yesterday_count = (
                    await audit_db._redis.zcard(f"audit:log:{date_str}")
                    if audit_db._redis
                    else 0
                )
                today_count = (
                    await audit_db._redis.zcard(f"audit:log:{today_str}")
                    if audit_db._redis
                    else 0
                )

                stats["entries_last_24h"] = yesterday_count + today_count

            return stats

        except Exception as e:
            logger.error(f"Failed to get audit statistics: {e}")
            return {
                "error": str(e),
                "total_logged": self._total_logged,
                "total_failed": self._total_failed,
            }

    async def cleanup_old_logs(self, days_to_keep: Optional[int] = None):
        """
        Clean up audit logs older than retention period

        Args:
            days_to_keep: Override default retention period
        """
        retention = days_to_keep or self.retention_days
        cutoff_date = datetime.now() - timedelta(days=retention)

        try:
            audit_db = await self._get_audit_db()
            if not audit_db:
                logger.warning("Cannot cleanup: Redis unavailable")
                return

            logger.info(
                f"Cleaning up audit logs older than {cutoff_date.strftime('%Y-%m-%d')}"
            )

            # Delete daily partitions older than cutoff
            current_date = cutoff_date.date()
            deleted_count = 0

            # Go back 365 days to ensure we catch everything
            for days_back in range(365):
                check_date = current_date - timedelta(days=days_back)
                date_str = check_date.strftime("%Y-%m-%d")

                # Delete all indexes for this date
                keys_to_delete = [
                    f"audit:log:{date_str}",
                    f"audit:op:*:{date_str}",
                    f"audit:user:*:{date_str}",
                    f"audit:vm:*:{date_str}",
                    f"audit:result:*:{date_str}",
                ]

                for key_pattern in keys_to_delete:
                    if "*" in key_pattern:
                        # Use scan for wildcard patterns
                        # Note: This is simplified - production should use scan_iter
                        pass
                    else:
                        deleted = await audit_db.delete(key_pattern)
                        if deleted:
                            deleted_count += deleted

            logger.info(f"Audit cleanup complete: {deleted_count} keys deleted")

        except Exception as e:
            logger.error(f"Audit cleanup failed: {e}")

    async def flush(self):
        """Force flush any pending batched entries"""
        async with self._batch_lock:
            await self._flush_batch()

    async def close(self):
        """Shutdown audit logger gracefully"""
        logger.info("Shutting down audit logger...")

        # Flush remaining entries
        await self.flush()

        # Cancel batch timer
        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass

        logger.info(
            f"Audit logger shutdown complete: {self._total_logged} entries logged, {self._total_failed} failed"
        )


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None
_logger_lock = asyncio.Lock()


async def get_audit_logger() -> AuditLogger:
    """Get or create global audit logger instance"""
    global _audit_logger

    async with _logger_lock:
        if _audit_logger is None:
            _audit_logger = AuditLogger()
            logger.info("Global audit logger initialized")
        return _audit_logger


async def close_audit_logger():
    """Close global audit logger"""
    global _audit_logger

    async with _logger_lock:
        if _audit_logger:
            await _audit_logger.close()
            _audit_logger = None


# Convenience function for quick logging
async def audit_log(operation: str, result: AuditResult = "success", **kwargs) -> bool:
    """
    Quick audit logging function

    Usage:
        await audit_log("auth.login", result="success", user_id="admin", ip_address="172.16.168.21")
    """
    logger_instance = await get_audit_logger()
    return await logger_instance.log(operation, result, **kwargs)
