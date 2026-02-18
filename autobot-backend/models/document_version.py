# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Document Version Tracking Model

Tracks changes, versions, and lifecycle events for knowledge base documents.
Enables incremental updates, host-specific tracking, and change detection.
"""

import asyncio
import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from backend.type_defs.common import Metadata


class ChangeType(str, Enum):
    """Document change types"""

    ADDED = "added"
    UPDATED = "updated"
    REMOVED = "removed"
    RESTORED = "restored"
    MIGRATED = "migrated"


@dataclass
class DocumentVersion:
    """
    Tracks a single version of a document with change metadata.

    Attributes:
        document_id: Unique identifier for the document
        version: Sequential version number (1, 2, 3, ...)
        content_hash: SHA256 hash of document content for change detection
        machine_id: Host/machine identifier where document exists
        os_type: Operating system type (linux, windows, macos)
        os_version: Specific OS version (e.g., "Ubuntu 22.04")
        created_at: Timestamp when this version was created
        change_type: Type of change (added, updated, removed, etc.)
        previous_hash: Content hash of previous version (for diffing)
        metadata: Additional metadata (source, command, category, etc.)
    """

    document_id: str
    version: int
    content_hash: str
    machine_id: str
    os_type: str
    created_at: datetime
    change_type: ChangeType

    # Optional fields
    os_version: Optional[str] = None
    previous_hash: Optional[str] = None
    metadata: Metadata = field(default_factory=dict)
    content_size: Optional[int] = None
    vectorized: bool = False
    vector_id: Optional[str] = None

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """
        Compute SHA256 hash of content for change detection.

        Args:
            content: Document content to hash

        Returns:
            Hex string of SHA256 hash
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def detect_change_type(
        old_hash: Optional[str], new_hash: Optional[str]
    ) -> ChangeType:
        """
        Automatically detect change type based on content hashes.

        Args:
            old_hash: Previous content hash (None if document is new)
            new_hash: New content hash (None if document removed)

        Returns:
            Detected change type
        """
        if old_hash is None and new_hash is not None:
            return ChangeType.ADDED
        elif old_hash is not None and new_hash is None:
            return ChangeType.REMOVED
        elif old_hash != new_hash:
            return ChangeType.UPDATED
        else:
            # Hashes match - no change
            return ChangeType.UPDATED  # Metadata update only

    def to_dict(self) -> Metadata:
        """Convert to dictionary for storage"""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["change_type"] = self.change_type.value
        return data

    @classmethod
    def from_dict(cls, data: Metadata) -> "DocumentVersion":
        """Create from dictionary"""
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["change_type"] = ChangeType(data["change_type"])
        return cls(**data)

    def is_content_changed(self, new_content: str) -> bool:
        """
        Check if new content is different from this version.

        Args:
            new_content: Content to compare against

        Returns:
            True if content has changed, False otherwise
        """
        new_hash = self.compute_content_hash(new_content)
        return new_hash != self.content_hash

    def get_version_summary(self) -> str:
        """Get human-readable version summary"""
        return (
            f"v{self.version} ({self.change_type.value}) - "
            f"{self.machine_id} - "
            f"{self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )


@dataclass
class DocumentChangeEvent:
    """
    Represents a change event to be broadcast to frontend.

    Used for real-time notifications via WebSocket/SSE.
    """

    event_id: str
    document_id: str
    document_title: str
    change_type: ChangeType
    machine_id: str
    os_type: str
    timestamp: datetime

    # Optional details
    category: Optional[str] = None
    affected_hosts: list = field(default_factory=list)
    version_number: Optional[int] = None
    content_preview: Optional[str] = None

    def to_dict(self) -> Metadata:
        """Convert to dictionary for JSON serialization"""
        return {
            "event_id": self.event_id,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "change_type": self.change_type.value,
            "machine_id": self.machine_id,
            "os_type": self.os_type,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category,
            "affected_hosts": self.affected_hosts,
            "version_number": self.version_number,
            "content_preview": self.content_preview,
        }


class DocumentChangeTracker:
    """
    Manages document version tracking and change detection.

    Stores version history in Redis and provides methods for:
    - Detecting content changes
    - Recording version history
    - Querying change history
    - Cross-host tracking
    """

    def __init__(self, redis_client):
        """
        Initialize change tracker with Redis client.

        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client
        self.VERSION_KEY_PREFIX = "doc:version:"
        self.HOST_DOCS_KEY_PREFIX = "host:docs:"
        self.DOC_HOSTS_KEY_PREFIX = "doc:hosts:"
        self.CHANGES_STREAM = "knowledge:changes"

    async def record_version(
        self,
        document_id: str,
        content: str,
        machine_id: str,
        os_type: str,
        change_type: ChangeType,
        metadata: Optional[Metadata] = None,
        os_version: Optional[str] = None,
    ) -> DocumentVersion:
        """
        Record a new document version.

        Args:
            document_id: Document identifier
            content: Document content
            machine_id: Host machine ID
            os_type: Operating system type
            change_type: Type of change
            metadata: Additional metadata
            os_version: OS version string

        Returns:
            Created DocumentVersion instance
        """
        # Get current version number
        current_version = await self.get_latest_version_number(document_id)
        new_version = current_version + 1

        # Get previous hash for diffing
        previous_hash = None
        if current_version > 0:
            prev_version = await self.get_version(document_id, current_version)
            if prev_version:
                previous_hash = prev_version.content_hash

        # Create new version
        version = DocumentVersion(
            document_id=document_id,
            version=new_version,
            content_hash=DocumentVersion.compute_content_hash(content),
            machine_id=machine_id,
            os_type=os_type,
            os_version=os_version,
            created_at=datetime.utcnow(),
            change_type=change_type,
            previous_hash=previous_hash,
            metadata=metadata or {},
            content_size=len(content),
        )

        # Store version in Redis (Issue #361 - avoid blocking)
        version_key = f"{self.VERSION_KEY_PREFIX}{document_id}:v{new_version}"
        host_key = f"{self.HOST_DOCS_KEY_PREFIX}{machine_id}"
        doc_hosts_key = f"{self.DOC_HOSTS_KEY_PREFIX}{document_id}"
        version_data = version.to_dict()

        def _store_version():
            self.redis.hset(version_key, mapping=version_data)
            self.redis.sadd(host_key, document_id)
            self.redis.sadd(doc_hosts_key, machine_id)
            self.redis.set(f"doc:latest_version:{document_id}", new_version)

        await asyncio.to_thread(_store_version)

        return version

    async def get_latest_version_number(self, document_id: str) -> int:
        """Get the latest version number for a document"""
        # Issue #361 - avoid blocking
        version = await asyncio.to_thread(
            self.redis.get, f"doc:latest_version:{document_id}"
        )
        return int(version) if version else 0

    async def get_version(
        self, document_id: str, version_number: int
    ) -> Optional[DocumentVersion]:
        """Get a specific version of a document"""
        version_key = f"{self.VERSION_KEY_PREFIX}{document_id}:v{version_number}"
        # Issue #361 - avoid blocking
        data = await asyncio.to_thread(self.redis.hgetall, version_key)

        if not data:
            return None

        return DocumentVersion.from_dict(data)

    async def get_version_history(
        self, document_id: str, limit: int = 10
    ) -> list[DocumentVersion]:
        """Get version history for a document"""
        latest_version = await self.get_latest_version_number(document_id)
        versions = []

        for version_num in range(latest_version, max(0, latest_version - limit), -1):
            version = await self.get_version(document_id, version_num)
            if version:
                versions.append(version)

        return versions

    async def get_host_documents(self, machine_id: str) -> set:
        """Get all document IDs for a specific host"""
        host_key = f"{self.HOST_DOCS_KEY_PREFIX}{machine_id}"
        return self.redis.smembers(host_key)

    async def get_document_hosts(self, document_id: str) -> set:
        """Get all hosts that have this document"""
        doc_hosts_key = f"{self.DOC_HOSTS_KEY_PREFIX}{document_id}"
        return self.redis.smembers(doc_hosts_key)

    async def emit_change_event(self, event: DocumentChangeEvent) -> None:
        """
        Emit a change event to Redis Streams for real-time notifications.

        Args:
            event: Change event to broadcast
        """
        self.redis.xadd(
            self.CHANGES_STREAM, event.to_dict(), maxlen=1000  # Keep last 1000 events
        )

    async def check_content_changed(
        self, document_id: str, new_content: str
    ) -> tuple[bool, Optional[str]]:
        """
        Check if document content has changed.

        Args:
            document_id: Document to check
            new_content: New content to compare

        Returns:
            Tuple of (has_changed, old_hash)
        """
        latest_version_num = await self.get_latest_version_number(document_id)

        if latest_version_num == 0:
            # New document
            return True, None

        latest_version = await self.get_version(document_id, latest_version_num)
        if not latest_version:
            return True, None

        new_hash = DocumentVersion.compute_content_hash(new_content)
        return (new_hash != latest_version.content_hash, latest_version.content_hash)
