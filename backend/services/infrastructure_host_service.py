# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Infrastructure Host Service

Manages user-defined infrastructure hosts (SSH/VNC) stored as secrets.
Provides host listing, connection info retrieval, and knowledge base integration.

Related Issue: #715 - Dynamic SSH/VNC host management via secrets
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.services.secrets_service import SecretsService, get_secrets_service
from backend.type_defs.common import Metadata

logger = logging.getLogger(__name__)

# Secret type identifier for infrastructure hosts
INFRASTRUCTURE_HOST_SECRET_TYPE = "infrastructure_host"


class HostCapability(str, Enum):
    """Capabilities a host can have."""

    SSH = "ssh"
    VNC = "vnc"


class AuthType(str, Enum):
    """Authentication types for SSH connections."""

    SSH_KEY = "ssh_key"
    PASSWORD = "password"


@dataclass
class InfrastructureHost:
    """Represents an infrastructure host configuration."""

    id: str
    name: str
    description: Optional[str]
    host: str
    ssh_port: int
    vnc_port: Optional[int]
    capabilities: List[HostCapability]
    tags: List[str]
    os: Optional[str]
    purpose: Optional[str]
    username: str
    auth_type: AuthType
    commands_extracted: bool
    last_connected: Optional[str]
    connection_count: int
    created_at: str
    updated_at: str
    scope: str
    chat_id: Optional[str]

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "host": self.host,
            "ssh_port": self.ssh_port,
            "vnc_port": self.vnc_port,
            "capabilities": [c.value if isinstance(c, HostCapability) else c for c in self.capabilities],
            "tags": self.tags,
            "os": self.os,
            "purpose": self.purpose,
            "username": self.username,
            "auth_type": self.auth_type.value if isinstance(self.auth_type, AuthType) else self.auth_type,
            "commands_extracted": self.commands_extracted,
            "last_connected": self.last_connected,
            "connection_count": self.connection_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "scope": self.scope,
            "chat_id": self.chat_id,
        }
        return result

    @classmethod
    def from_secret(cls, secret: Dict[str, Any], include_credentials: bool = False) -> "InfrastructureHost":
        """Create InfrastructureHost from a secret dictionary."""
        metadata = secret.get("metadata", {})

        # Parse capabilities
        raw_capabilities = metadata.get("capabilities", ["ssh"])
        capabilities = []
        for cap in raw_capabilities:
            if isinstance(cap, HostCapability):
                capabilities.append(cap)
            elif cap in [c.value for c in HostCapability]:
                capabilities.append(HostCapability(cap))

        # Parse auth type
        raw_auth_type = metadata.get("auth_type", "ssh_key")
        if isinstance(raw_auth_type, AuthType):
            auth_type = raw_auth_type
        else:
            auth_type = AuthType(raw_auth_type) if raw_auth_type in [a.value for a in AuthType] else AuthType.SSH_KEY

        return cls(
            id=secret["id"],
            name=secret["name"],
            description=secret.get("description"),
            host=metadata.get("host", ""),
            ssh_port=metadata.get("ssh_port", 22),
            vnc_port=metadata.get("vnc_port"),
            capabilities=capabilities,
            tags=metadata.get("tags", []),
            os=metadata.get("os"),
            purpose=metadata.get("purpose"),
            username=metadata.get("username", "root"),
            auth_type=auth_type,
            commands_extracted=metadata.get("commands_extracted", False),
            last_connected=metadata.get("last_connected"),
            connection_count=metadata.get("connection_count", 0),
            created_at=secret.get("created_at", ""),
            updated_at=secret.get("updated_at", ""),
            scope=secret.get("scope", "general"),
            chat_id=secret.get("chat_id"),
        )


class InfrastructureHostService:
    """Service for managing infrastructure hosts."""

    def __init__(self, secrets_service: Optional[SecretsService] = None):
        """Initialize the infrastructure host service."""
        self._secrets_service = secrets_service

    @property
    def secrets_service(self) -> SecretsService:
        """Get secrets service (lazy initialization)."""
        if self._secrets_service is None:
            self._secrets_service = get_secrets_service()
        return self._secrets_service

    def create_host(
        self,
        name: str,
        host: str,
        username: str,
        auth_type: AuthType = AuthType.SSH_KEY,
        ssh_key: Optional[str] = None,
        ssh_key_passphrase: Optional[str] = None,
        ssh_password: Optional[str] = None,
        vnc_password: Optional[str] = None,
        ssh_port: int = 22,
        vnc_port: Optional[int] = None,
        capabilities: Optional[List[HostCapability]] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        os: Optional[str] = None,
        purpose: Optional[str] = None,
        scope: str = "general",
        chat_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Metadata:
        """
        Create a new infrastructure host.

        Args:
            name: Unique name for the host
            host: IP address or hostname
            username: SSH username
            auth_type: Authentication type (ssh_key or password)
            ssh_key: SSH private key content (if auth_type is ssh_key)
            ssh_key_passphrase: Passphrase for encrypted SSH key
            ssh_password: SSH password (if auth_type is password)
            vnc_password: VNC password (if VNC capability enabled)
            ssh_port: SSH port (default 22)
            vnc_port: VNC port (if VNC capability enabled)
            capabilities: List of capabilities (ssh, vnc)
            description: Human-readable description
            tags: List of tags for categorization
            os: Operating system info
            purpose: Purpose/role of the host
            scope: Secret scope (general or chat)
            chat_id: Chat ID if scope is chat
            created_by: User who created this host

        Returns:
            Created host metadata
        """
        if capabilities is None:
            capabilities = [HostCapability.SSH]

        # Build encrypted value (credentials)
        encrypted_value = {
            "auth_type": auth_type.value if isinstance(auth_type, AuthType) else auth_type,
            "username": username,
        }

        if auth_type == AuthType.SSH_KEY or auth_type == "ssh_key":
            if not ssh_key:
                raise ValueError("SSH key is required when auth_type is ssh_key")
            encrypted_value["ssh_key"] = ssh_key
            if ssh_key_passphrase:
                encrypted_value["ssh_key_passphrase"] = ssh_key_passphrase
        else:
            if not ssh_password:
                raise ValueError("SSH password is required when auth_type is password")
            encrypted_value["ssh_password"] = ssh_password

        if vnc_password:
            encrypted_value["vnc_password"] = vnc_password

        # Build metadata (non-sensitive connection info)
        metadata = {
            "host": host,
            "ssh_port": ssh_port,
            "vnc_port": vnc_port,
            "capabilities": [c.value if isinstance(c, HostCapability) else c for c in capabilities],
            "username": username,
            "auth_type": auth_type.value if isinstance(auth_type, AuthType) else auth_type,
            "tags": tags or [],
            "os": os,
            "purpose": purpose,
            "commands_extracted": False,
            "last_connected": None,
            "connection_count": 0,
        }

        # Create the secret
        result = self.secrets_service.create_secret(
            name=name,
            secret_type=INFRASTRUCTURE_HOST_SECRET_TYPE,
            value=json.dumps(encrypted_value),
            scope=scope,
            chat_id=chat_id,
            description=description,
            metadata=metadata,
            created_by=created_by,
        )

        logger.info("Created infrastructure host: %s (%s)", name, result.get("id"))
        return result

    def list_hosts(
        self,
        capability: Optional[HostCapability] = None,
        scope: Optional[str] = None,
        chat_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[InfrastructureHost]:
        """
        List infrastructure hosts with optional filtering.

        Args:
            capability: Filter by capability (ssh or vnc)
            scope: Filter by scope (general or chat)
            chat_id: Filter by chat ID
            tags: Filter by tags (host must have all specified tags)

        Returns:
            List of InfrastructureHost objects
        """
        secrets = self.secrets_service.list_secrets(
            secret_type=INFRASTRUCTURE_HOST_SECRET_TYPE,
            scope=scope,
            chat_id=chat_id,
        )

        hosts = []
        for secret in secrets:
            # Get full secret with metadata
            full_secret = self.secrets_service.get_secret(
                secret_id=secret["id"],
                include_value=False,
            )
            if not full_secret:
                continue

            host = InfrastructureHost.from_secret(full_secret)

            # Apply capability filter
            if capability and capability not in host.capabilities:
                continue

            # Apply tags filter
            if tags:
                if not all(tag in host.tags for tag in tags):
                    continue

            hosts.append(host)

        return hosts

    def get_host(self, host_id: str, include_credentials: bool = False) -> Optional[InfrastructureHost]:
        """
        Get a specific host by ID.

        Args:
            host_id: The host/secret ID
            include_credentials: Whether to include decrypted credentials

        Returns:
            InfrastructureHost or None if not found
        """
        secret = self.secrets_service.get_secret(
            secret_id=host_id,
            include_value=include_credentials,
        )

        if not secret:
            return None

        if secret.get("secret_type") != INFRASTRUCTURE_HOST_SECRET_TYPE:
            logger.warning("Secret %s is not an infrastructure host", host_id)
            return None

        return InfrastructureHost.from_secret(secret, include_credentials)

    def get_host_credentials(self, host_id: str, accessed_by: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get decrypted credentials for a host.

        Args:
            host_id: The host/secret ID
            accessed_by: User accessing the credentials (for audit)

        Returns:
            Decrypted credentials dict or None
        """
        secret = self.secrets_service.get_secret(
            secret_id=host_id,
            include_value=True,
            accessed_by=accessed_by,
        )

        if not secret:
            return None

        if secret.get("secret_type") != INFRASTRUCTURE_HOST_SECRET_TYPE:
            return None

        try:
            credentials = json.loads(secret.get("value", "{}"))
            # Add host info for convenience
            metadata = secret.get("metadata", {})
            credentials["host"] = metadata.get("host")
            credentials["ssh_port"] = metadata.get("ssh_port", 22)
            credentials["vnc_port"] = metadata.get("vnc_port")
            return credentials
        except json.JSONDecodeError:
            logger.error("Failed to parse credentials for host %s", host_id)
            return None

    def update_host(
        self,
        host_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        host: Optional[str] = None,
        ssh_port: Optional[int] = None,
        vnc_port: Optional[int] = None,
        capabilities: Optional[List[HostCapability]] = None,
        tags: Optional[List[str]] = None,
        os: Optional[str] = None,
        purpose: Optional[str] = None,
        ssh_key: Optional[str] = None,
        ssh_password: Optional[str] = None,
        vnc_password: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> bool:
        """
        Update an infrastructure host.

        Args:
            host_id: The host/secret ID
            name: New name (optional)
            description: New description (optional)
            host: New hostname/IP (optional)
            ssh_port: New SSH port (optional)
            vnc_port: New VNC port (optional)
            capabilities: New capabilities (optional)
            tags: New tags (optional)
            os: New OS info (optional)
            purpose: New purpose (optional)
            ssh_key: New SSH key (optional)
            ssh_password: New SSH password (optional)
            vnc_password: New VNC password (optional)
            updated_by: User making the update

        Returns:
            True if updated successfully
        """
        # Get current secret
        current = self.secrets_service.get_secret(secret_id=host_id, include_value=True)
        if not current or current.get("secret_type") != INFRASTRUCTURE_HOST_SECRET_TYPE:
            return False

        # Update metadata if needed
        new_metadata = None
        current_metadata = current.get("metadata", {})

        metadata_updates = {}
        if host is not None:
            metadata_updates["host"] = host
        if ssh_port is not None:
            metadata_updates["ssh_port"] = ssh_port
        if vnc_port is not None:
            metadata_updates["vnc_port"] = vnc_port
        if capabilities is not None:
            metadata_updates["capabilities"] = [c.value if isinstance(c, HostCapability) else c for c in capabilities]
        if tags is not None:
            metadata_updates["tags"] = tags
        if os is not None:
            metadata_updates["os"] = os
        if purpose is not None:
            metadata_updates["purpose"] = purpose

        if metadata_updates:
            new_metadata = {**current_metadata, **metadata_updates}

        # Update credentials if needed
        new_value = None
        if ssh_key is not None or ssh_password is not None or vnc_password is not None:
            try:
                current_creds = json.loads(current.get("value", "{}"))
            except json.JSONDecodeError:
                current_creds = {}

            if ssh_key is not None:
                current_creds["ssh_key"] = ssh_key
                current_creds["auth_type"] = "ssh_key"
            if ssh_password is not None:
                current_creds["ssh_password"] = ssh_password
                current_creds["auth_type"] = "password"
            if vnc_password is not None:
                current_creds["vnc_password"] = vnc_password

            new_value = json.dumps(current_creds)

        return self.secrets_service.update_secret(
            secret_id=host_id,
            name=name,
            description=description,
            value=new_value,
            metadata=new_metadata,
            updated_by=updated_by,
        )

    def delete_host(self, host_id: str, hard_delete: bool = False, deleted_by: Optional[str] = None) -> bool:
        """
        Delete an infrastructure host.

        Args:
            host_id: The host/secret ID
            hard_delete: If True, permanently delete. If False, soft delete.
            deleted_by: User deleting the host

        Returns:
            True if deleted successfully
        """
        # Verify it's an infrastructure host
        host = self.get_host(host_id)
        if not host:
            return False

        return self.secrets_service.delete_secret(
            secret_id=host_id,
            hard_delete=hard_delete,
            deleted_by=deleted_by,
        )

    def record_connection(self, host_id: str) -> bool:
        """
        Record a connection to a host (updates last_connected and connection_count).

        Args:
            host_id: The host/secret ID

        Returns:
            True if recorded successfully
        """
        current = self.secrets_service.get_secret(secret_id=host_id, include_value=False)
        if not current or current.get("secret_type") != INFRASTRUCTURE_HOST_SECRET_TYPE:
            return False

        metadata = current.get("metadata", {})
        metadata["last_connected"] = datetime.now(timezone.utc).isoformat()
        metadata["connection_count"] = metadata.get("connection_count", 0) + 1

        return self.secrets_service.update_secret(
            secret_id=host_id,
            metadata=metadata,
            updated_by="system",
        )

    def mark_commands_extracted(self, host_id: str) -> bool:
        """
        Mark a host as having had its commands extracted.

        Args:
            host_id: The host/secret ID

        Returns:
            True if marked successfully
        """
        current = self.secrets_service.get_secret(secret_id=host_id, include_value=False)
        if not current or current.get("secret_type") != INFRASTRUCTURE_HOST_SECRET_TYPE:
            return False

        metadata = current.get("metadata", {})
        metadata["commands_extracted"] = True
        metadata["commands_extracted_at"] = datetime.now(timezone.utc).isoformat()

        return self.secrets_service.update_secret(
            secret_id=host_id,
            metadata=metadata,
            updated_by="system",
        )

    async def test_connection(self, host_id: str, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Test SSH and VNC connectivity to a host.

        Args:
            host_id: The host/secret ID
            timeout: Connection timeout in seconds

        Returns:
            Connection test results
        """
        host = self.get_host(host_id)
        if not host:
            return {"success": False, "error": "Host not found"}

        results = {
            "success": True,
            "host": host.host,
            "ssh_available": False,
            "vnc_available": False,
            "ssh_error": None,
            "vnc_error": None,
            "latency_ms": None,
        }

        # Test SSH connectivity (port check)
        if HostCapability.SSH in host.capabilities:
            ssh_result = await self._test_port(host.host, host.ssh_port, timeout)
            results["ssh_available"] = ssh_result["available"]
            results["ssh_error"] = ssh_result.get("error")
            if ssh_result.get("latency_ms"):
                results["latency_ms"] = ssh_result["latency_ms"]

        # Test VNC connectivity (port check)
        if HostCapability.VNC in host.capabilities and host.vnc_port:
            vnc_result = await self._test_port(host.host, host.vnc_port, timeout)
            results["vnc_available"] = vnc_result["available"]
            results["vnc_error"] = vnc_result.get("error")

        # Overall success if at least one capability is available
        results["success"] = results["ssh_available"] or results["vnc_available"]

        return results

    async def _test_port(self, host: str, port: int, timeout: float) -> Dict[str, Any]:
        """Test if a port is reachable."""
        import time

        start_time = time.time()
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )
            latency_ms = (time.time() - start_time) * 1000
            writer.close()
            await writer.wait_closed()
            return {"available": True, "latency_ms": round(latency_ms, 2)}
        except asyncio.TimeoutError:
            return {"available": False, "error": "Connection timed out"}
        except ConnectionRefusedError:
            return {"available": False, "error": "Connection refused"}
        except OSError as e:
            return {"available": False, "error": str(e)}


# Singleton instance
import threading

_infrastructure_host_service: Optional[InfrastructureHostService] = None
_infrastructure_host_service_lock = threading.Lock()


def get_infrastructure_host_service() -> InfrastructureHostService:
    """Get or create the infrastructure host service singleton."""
    global _infrastructure_host_service
    if _infrastructure_host_service is None:
        with _infrastructure_host_service_lock:
            if _infrastructure_host_service is None:
                _infrastructure_host_service = InfrastructureHostService()
    return _infrastructure_host_service


def reset_infrastructure_host_service() -> None:
    """Reset the infrastructure host service singleton.

    Use this when the underlying secrets service has been reset and needs
    to be reinitialized.
    """
    global _infrastructure_host_service
    with _infrastructure_host_service_lock:
        _infrastructure_host_service = None
        logger.info("InfrastructureHostService singleton reset")
