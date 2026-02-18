# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Audit Logging

Issue #679: Comprehensive audit trail for knowledge access, modifications, and permission changes.
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of auditable events."""

    # Access events
    VIEW = "view"
    SEARCH = "search"
    DOWNLOAD = "download"

    # Modification events
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

    # Permission events
    SHARE = "share"
    UNSHARE = "unshare"
    CHANGE_VISIBILITY = "change_visibility"
    CHANGE_OWNER = "change_owner"

    # Administrative events
    POLICY_UPDATE = "policy_update"
    BULK_DELETE = "bulk_delete"
    EXPORT = "export"


class KnowledgeAuditLog:
    """Manages audit logging for knowledge base operations.

    Issue #679: Stores audit events in Redis with TTL and provides query methods.
    """

    def __init__(self, redis_client, ttl_days: int = 365):
        """Initialize audit log.

        Args:
            redis_client: Redis client instance (sync)
            ttl_days: Days to retain audit logs (default: 1 year)
        """
        self.redis_client = redis_client
        self.ttl_seconds = ttl_days * 24 * 60 * 60
        logger.info("KnowledgeAuditLog initialized with %d day retention", ttl_days)

    async def log_event(
        self,
        event_type: AuditEventType,
        user_id: str,
        fact_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        details: Optional[Dict] = None,
        ip_address: Optional[str] = None,
    ) -> str:
        """Log an audit event.

        Args:
            event_type: Type of event
            user_id: User who performed the action
            fact_id: Fact ID if applicable
            organization_id: Organization ID if applicable
            details: Additional event details
            ip_address: User's IP address

        Returns:
            Event ID
        """
        event_id = f"audit:{datetime.utcnow().timestamp()}"
        event_data = {
            "id": event_id,
            "type": event_type,
            "user_id": user_id,
            "fact_id": fact_id,
            "organization_id": organization_id,
            "details": details or {},
            "ip_address": ip_address,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Store event in Redis
        await asyncio.to_thread(
            self.redis_client.setex,
            event_id,
            self.ttl_seconds,
            json.dumps(event_data),
        )

        # Add to user's activity index
        user_key = f"audit:user:{user_id}"
        await asyncio.to_thread(
            self.redis_client.zadd, user_key, {event_id: datetime.utcnow().timestamp()}
        )
        await asyncio.to_thread(self.redis_client.expire, user_key, self.ttl_seconds)

        # Add to fact's access log if fact_id provided
        if fact_id:
            fact_key = f"audit:fact:{fact_id}"
            await asyncio.to_thread(
                self.redis_client.zadd,
                fact_key,
                {event_id: datetime.utcnow().timestamp()},
            )
            await asyncio.to_thread(
                self.redis_client.expire, fact_key, self.ttl_seconds
            )

        # Add to organization's audit log if org_id provided
        if organization_id:
            org_key = f"audit:org:{organization_id}"
            await asyncio.to_thread(
                self.redis_client.zadd,
                org_key,
                {event_id: datetime.utcnow().timestamp()},
            )
            await asyncio.to_thread(self.redis_client.expire, org_key, self.ttl_seconds)

        logger.debug(
            "Logged audit event: type=%s, user=%s, fact=%s",
            event_type,
            user_id,
            fact_id,
        )

        return event_id

    async def get_user_activity(
        self, user_id: str, limit: int = 100, offset: int = 0
    ) -> List[Dict]:
        """Get audit events for a user.

        Args:
            user_id: User ID
            limit: Maximum events to return
            offset: Pagination offset

        Returns:
            List of audit event dicts
        """
        user_key = f"audit:user:{user_id}"

        # Get event IDs sorted by timestamp (newest first)
        event_ids = await asyncio.to_thread(
            self.redis_client.zrevrange, user_key, offset, offset + limit - 1
        )

        # Fetch event data
        events = []
        for event_id in event_ids:
            if isinstance(event_id, bytes):
                event_id = event_id.decode("utf-8")

            event_data = await asyncio.to_thread(self.redis_client.get, event_id)
            if event_data:
                if isinstance(event_data, bytes):
                    event_data = event_data.decode("utf-8")
                events.append(json.loads(event_data))

        return events

    async def get_fact_access_log(self, fact_id: str, limit: int = 100) -> List[Dict]:
        """Get audit events for a specific fact.

        Args:
            fact_id: Fact ID
            limit: Maximum events to return

        Returns:
            List of audit event dicts
        """
        fact_key = f"audit:fact:{fact_id}"

        # Get event IDs sorted by timestamp (newest first)
        event_ids = await asyncio.to_thread(
            self.redis_client.zrevrange, fact_key, 0, limit - 1
        )

        # Fetch event data
        events = []
        for event_id in event_ids:
            if isinstance(event_id, bytes):
                event_id = event_id.decode("utf-8")

            event_data = await asyncio.to_thread(self.redis_client.get, event_id)
            if event_data:
                if isinstance(event_data, bytes):
                    event_data = event_data.decode("utf-8")
                events.append(json.loads(event_data))

        return events

    async def get_organization_audit_log(
        self, organization_id: str, limit: int = 1000, offset: int = 0
    ) -> List[Dict]:
        """Get audit events for an organization.

        Args:
            organization_id: Organization ID
            limit: Maximum events to return
            offset: Pagination offset

        Returns:
            List of audit event dicts
        """
        org_key = f"audit:org:{organization_id}"

        # Get event IDs sorted by timestamp (newest first)
        event_ids = await asyncio.to_thread(
            self.redis_client.zrevrange, org_key, offset, offset + limit - 1
        )

        # Fetch event data
        events = []
        for event_id in event_ids:
            if isinstance(event_id, bytes):
                event_id = event_id.decode("utf-8")

            event_data = await asyncio.to_thread(self.redis_client.get, event_id)
            if event_data:
                if isinstance(event_data, bytes):
                    event_data = event_data.decode("utf-8")
                events.append(json.loads(event_data))

        return events

    async def get_permission_changes(
        self,
        fact_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Get permission change events.

        Args:
            fact_id: Filter by fact ID
            user_id: Filter by user who made changes
            limit: Maximum events to return

        Returns:
            List of permission change event dicts
        """
        permission_event_types = {
            AuditEventType.SHARE,
            AuditEventType.UNSHARE,
            AuditEventType.CHANGE_VISIBILITY,
            AuditEventType.CHANGE_OWNER,
        }

        if fact_id:
            # Get all events for this fact and filter
            all_events = await self.get_fact_access_log(fact_id, limit=limit)
        elif user_id:
            # Get all events by this user and filter
            all_events = await self.get_user_activity(user_id, limit=limit)
        else:
            # No filter provided
            return []

        # Filter for permission events
        permission_events = [
            event for event in all_events if event.get("type") in permission_event_types
        ]

        return permission_events[:limit]

    async def generate_compliance_report(
        self, organization_id: str, start_date: datetime, end_date: datetime
    ) -> Dict:
        """Generate compliance report for an organization.

        Args:
            organization_id: Organization ID
            start_date: Report start date
            end_date: Report end date

        Returns:
            Compliance report dict with statistics
        """
        # Get all org events in date range
        org_key = f"audit:org:{organization_id}"

        start_ts = start_date.timestamp()
        end_ts = end_date.timestamp()

        event_ids = await asyncio.to_thread(
            self.redis_client.zrangebyscore, org_key, start_ts, end_ts
        )

        # Fetch and analyze events
        events = []
        for event_id in event_ids:
            if isinstance(event_id, bytes):
                event_id = event_id.decode("utf-8")

            event_data = await asyncio.to_thread(self.redis_client.get, event_id)
            if event_data:
                if isinstance(event_data, bytes):
                    event_data = event_data.decode("utf-8")
                events.append(json.loads(event_data))

        # Compute statistics
        event_counts = {}
        user_activity = {}
        fact_modifications = {}

        for event in events:
            # Count by type
            event_type = event.get("type")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

            # Count by user
            user_id = event.get("user_id")
            if user_id:
                user_activity[user_id] = user_activity.get(user_id, 0) + 1

            # Track fact modifications
            fact_id = event.get("fact_id")
            if fact_id and event_type in {
                AuditEventType.CREATE,
                AuditEventType.UPDATE,
                AuditEventType.DELETE,
            }:
                if fact_id not in fact_modifications:
                    fact_modifications[fact_id] = []
                fact_modifications[fact_id].append(event)

        return {
            "organization_id": organization_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_events": len(events),
            "event_counts": event_counts,
            "unique_users": len(user_activity),
            "most_active_users": sorted(
                [
                    {"user_id": uid, "count": count}
                    for uid, count in user_activity.items()
                ],
                key=lambda x: x["count"],
                reverse=True,
            )[:10],
            "facts_modified": len(fact_modifications),
            "permission_changes": event_counts.get(AuditEventType.SHARE, 0)
            + event_counts.get(AuditEventType.UNSHARE, 0)
            + event_counts.get(AuditEventType.CHANGE_VISIBILITY, 0),
        }
