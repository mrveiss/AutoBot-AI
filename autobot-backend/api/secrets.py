# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# backend/api/secrets.py
"""
Secrets Management API

Provides comprehensive secrets management with dual scope:
- Chat-scoped secrets: Only accessible within originating conversation
- General-scoped secrets: Accessible across all chats
- Multiple secret types: SSH keys, passwords, API keys
- Transfer capability: Move chat secrets to general pool
- Cleanup management: Handle secrets on chat deletion
"""

import asyncio
import base64
import json
import os
import re
import threading
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from time import time
from typing import Dict, List

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from api.schemas_system import (
    ChatSecretsDeleteData,
    SecretCreatedData,
    SecretCreateRequest,
    SecretModel,
    SecretScope,
    SecretsListData,
    SecretsStatsData,
    SecretsStatusResponse,
    SecretTransferData,
    SecretTransferRequest,
    SecretType,
    SecretTypesData,
    SecretUpdateRequest,
)
from auth_middleware import check_admin_permission, get_auth_middleware
from autobot_memory_graph import AutoBotMemoryGraph
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import parse_utc_iso
from middleware.proxy_utils import get_client_ip
from services.audit.unified_audit import AuditAction, audit_record  # GH#8290 Phase 2
from type_defs.common import Metadata

logger = get_logger(__name__)

router = APIRouter()

# Security constants
SECRET_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 30  # max requests per window


class RateLimiter:
    """Simple in-memory rate limiter for secrets API"""

    def __init__(
        self,
        window: int = RATE_LIMIT_WINDOW,
        max_requests: int = RATE_LIMIT_MAX_REQUESTS,
    ):
        """Initialize rate limiter with window size and request limit."""
        self.window = window
        self.max_requests = max_requests
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed under rate limit"""
        now = time()
        # Clean old requests
        self.requests[client_id] = [t for t in self.requests[client_id] if now - t < self.window]
        # Check limit
        if len(self.requests[client_id]) >= self.max_requests:
            return False
        # Record request
        self.requests[client_id].append(now)
        return True

    def get_remaining(self, client_id: str) -> int:
        """Get remaining requests for client"""
        now = time()
        self.requests[client_id] = [t for t in self.requests[client_id] if now - t < self.window]
        return max(0, self.max_requests - len(self.requests[client_id]))


# Global rate limiter instance
rate_limiter = RateLimiter()


def validate_secret_name(name: str) -> str:
    """Validate and sanitize secret name"""
    if not SECRET_NAME_PATTERN.match(name):
        raise ValueError("Secret name must contain only alphanumeric characters, " "underscores, hyphens, and dots")
    return name


class SecretsManager:
    """Manages encrypted secrets with dual scope support"""

    def __init__(self):
        """Initialize secrets manager with encryption and caching."""
        # Use centralized path management
        from utils.paths_manager import ensure_data_directory, get_data_path

        # Ensure data directory exists
        ensure_data_directory()

        # Get paths using centralized configuration
        self.secrets_file = str(get_data_path("secrets.json"))
        self.key_file = str(get_data_path("secrets.key"))
        self._initialize_encryption()

        # Cache layer to reduce file I/O (Issue #327)
        self._secrets_cache: Dict[str, Dict] | None = None
        self._cache_lock = threading.RLock()  # Thread-safe access to cache
        self._cache_mtime: float | None = None  # Track file modification time

    def _ensure_directories(self):
        """Ensure data directory exists - now handled by centralized paths"""
        # This method is kept for compatibility but functionality moved to centralized paths
        from utils.paths_manager import ensure_data_directory

        ensure_data_directory()

    def _initialize_encryption(self):
        """Initialize or load encryption key"""
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            # Fernet key must persist to decrypt secrets on next startup;
            # secured by 0o600 file permissions.
            with open(self.key_file, "wb") as f:
                f.write(key)  # lgtm[py/clear-text-storage-sensitive-data]
            os.chmod(self.key_file, 0o600)  # Restrict permissions

        self.cipher = Fernet(key)

    def _encrypt_value(self, value: str) -> str:
        """Encrypt a secret value"""
        return base64.b64encode(self.cipher.encrypt(value.encode())).decode()

    def _decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a secret value"""
        return self.cipher.decrypt(base64.b64decode(encrypted_value.encode())).decode()

    def _load_secrets(self) -> Dict[str, Dict]:
        """
        Load secrets from encrypted storage with thread-safe caching (Issue #327).

        Uses in-memory cache to avoid repeated file reads with automatic
        invalidation if file is modified externally.

        Returns:
            Deep copy of secrets dict to prevent race conditions
        """
        with self._cache_lock:
            # Check if file exists
            if not os.path.exists(self.secrets_file):
                self._secrets_cache = {}
                self._cache_mtime = None
                return deepcopy(self._secrets_cache)

            # Get current file modification time
            try:
                current_mtime = os.path.getmtime(self.secrets_file)
            except OSError as e:
                logger.error("Failed to get secrets file mtime: %s", e)
                # File may have been deleted - return empty dict
                self._secrets_cache = {}
                self._cache_mtime = None
                return deepcopy(self._secrets_cache)

            # Check if cache is valid
            if self._secrets_cache is not None and self._cache_mtime == current_mtime:
                # Return deep copy to prevent race conditions
                return deepcopy(self._secrets_cache)

            # Cache miss or invalidated - reload from disk
            try:
                with open(self.secrets_file, "r", encoding="utf-8") as f:
                    self._secrets_cache = json.load(f)
                    self._cache_mtime = current_mtime
                    return deepcopy(self._secrets_cache)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logger.warning("Secrets file corrupted or missing: %s, initializing empty", e)
                self._secrets_cache = {}
                self._cache_mtime = None
                return deepcopy(self._secrets_cache)

    def _save_secrets(self, secrets: Dict[str, Dict]):
        """
        Save secrets to encrypted storage with thread-safe cache update (Issue #327).

        Writes to disk immediately and updates in-memory cache with current mtime.
        Thread-safe to prevent race conditions during concurrent writes.

        Args:
            secrets: Secrets dictionary to save
        """

        def json_serializer(obj):
            """Serialize datetime and other objects to JSON-compatible strings."""
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return str(obj)

        with self._cache_lock:
            with open(self.secrets_file, "w", encoding="utf-8") as f:
                # Values in `secrets` are Fernet-encrypted (stored as
                # `encrypted_value`); raw plaintext is never written to disk.
                # codeql[py/clear-text-storage-sensitive-data]
                # Fernet-encrypted `encrypted_value` fields — no plaintext secret is written.
                json.dump(secrets, f, indent=2, default=json_serializer)
            os.chmod(self.secrets_file, 0o600)  # Restrict permissions

            # Update cache and mtime after successful write
            self._secrets_cache = deepcopy(secrets)
            try:
                self._cache_mtime = os.path.getmtime(self.secrets_file)
            except OSError as e:
                logger.error("Failed to update cache mtime: %s", e)
                self._cache_mtime = None

    def _invalidate_cache(self):
        """
        Invalidate the secrets cache to force reload from disk (Issue #327).

        Thread-safe method to manually invalidate cache.
        Use when you know external processes have modified the secrets file.
        Note: Automatic mtime-based invalidation handles most cases.
        """
        with self._cache_lock:
            self._secrets_cache = None
            self._cache_mtime = None

    def create_secret(self, request: SecretCreateRequest) -> SecretModel:
        """Create a new secret (Issue #372 - uses model methods)."""
        secrets = self._load_secrets()

        # Validate scope and chat_id consistency using model methods (Issue #372)
        if request.requires_chat_id():
            raise ValueError("Chat-scoped secrets must have a chat_id")

        # Create secret model using model method (Issue #372)
        secret = request.to_secret_model()

        # Encrypt and store the secret value
        encrypted_value = self._encrypt_value(request.value)
        secret_data = secret.dict()
        secret_data["encrypted_value"] = encrypted_value

        secrets[secret.id] = secret_data
        self._save_secrets(secrets)

        # codeql[py/clear-text-logging-sensitive-data]
        logger.info("Created %s (ID: %s)", request.get_log_summary(), secret.id)
        return secret

    def get_secret(self, secret_id: str, chat_id: str | None = None) -> Dict | None:
        """Get a secret with access control"""
        secrets = self._load_secrets()
        secret_data = secrets.get(secret_id)

        if not secret_data:
            return None

        # Check access permissions
        if secret_data["scope"] == SecretScope.CHAT:
            if not chat_id or secret_data["chat_id"] != chat_id:
                raise PermissionError("Access denied: Chat-scoped secret from different chat")

        # Return secret with decrypted value
        secret_data = secret_data.copy()
        secret_data["value"] = self._decrypt_value(secret_data["encrypted_value"])
        del secret_data["encrypted_value"]

        return secret_data

    def list_secrets(self, chat_id: str | None = None, scope: SecretScope | None = None) -> List[Dict]:
        """List secrets with access control"""
        secrets = self._load_secrets()
        result = []

        for secret_id, secret_data in secrets.items():
            # Apply scope filter
            if scope and secret_data["scope"] != scope:
                continue

            # Apply access control
            if secret_data["scope"] == SecretScope.CHAT:
                if not chat_id or secret_data["chat_id"] != chat_id:
                    continue

            # Return metadata without encrypted value
            safe_data = secret_data.copy()
            del safe_data["encrypted_value"]
            safe_data["has_value"] = True
            result.append(safe_data)

        return result

    def update_secret(
        self,
        secret_id: str,
        request: SecretUpdateRequest,
        chat_id: str | None = None,
    ) -> SecretModel | None:
        """Update a secret with access control"""
        secrets = self._load_secrets()
        secret_data = secrets.get(secret_id)

        if not secret_data:
            return None

        # Check access permissions
        if secret_data["scope"] == SecretScope.CHAT:
            if not chat_id or secret_data["chat_id"] != chat_id:
                raise PermissionError("Access denied: Cannot modify chat-scoped secret from " "different chat")

        # Update fields
        if request.name is not None:
            secret_data["name"] = request.name
        if request.description is not None:
            secret_data["description"] = request.description
        if request.tags is not None:
            secret_data["tags"] = request.tags
        if request.expires_at is not None:
            secret_data["expires_at"] = request.expires_at.isoformat() if request.expires_at else None
        if request.metadata is not None:
            secret_data["metadata"] = request.metadata

        secret_data["updated_at"] = datetime.now(tz=timezone.utc).isoformat()

        secrets[secret_id] = secret_data
        self._save_secrets(secrets)

        logger.info("Updated secret (ID: %s...)", secret_id[:8])  # codeql[py/clear-text-logging-sensitive-data]

        # Return updated secret model
        safe_data = secret_data.copy()
        del safe_data["encrypted_value"]
        return SecretModel(**safe_data)

    def delete_secret(self, secret_id: str, chat_id: str | None = None) -> bool:
        """Delete a secret with access control"""
        secrets = self._load_secrets()
        secret_data = secrets.get(secret_id)

        if not secret_data:
            return False

        # Check access permissions
        if secret_data["scope"] == SecretScope.CHAT:
            if not chat_id or secret_data["chat_id"] != chat_id:
                raise PermissionError("Access denied: Cannot delete chat-scoped secret from " "different chat")

        del secrets[secret_id]
        self._save_secrets(secrets)

        logger.info("Deleted secret (ID: %s...)", secret_id[:8])  # codeql[py/clear-text-logging-sensitive-data]
        return True

    def transfer_secrets(self, request: SecretTransferRequest, chat_id: str | None = None) -> Metadata:
        """Transfer secrets between scopes"""
        secrets = self._load_secrets()
        transferred = []
        failed = []

        for secret_id in request.secret_ids:
            secret_data = secrets.get(secret_id)
            if not secret_data:
                failed.append({"secret_id": secret_id, "reason": "Secret not found"})
                continue

            # Check access permissions for source
            if secret_data["scope"] == SecretScope.CHAT:
                if not chat_id or secret_data["chat_id"] != chat_id:
                    failed.append({"secret_id": secret_id, "reason": "Access denied"})
                    continue

            # Validate target scope
            if request.target_scope == SecretScope.CHAT and not request.target_chat_id:
                failed.append(
                    {
                        "secret_id": secret_id,
                        "reason": "Target chat_id required for chat scope",
                    }
                )
                continue

            # Perform transfer
            secret_data["scope"] = request.target_scope
            if request.target_scope == SecretScope.CHAT:
                secret_data["chat_id"] = request.target_chat_id
            else:
                secret_data["chat_id"] = None

            secret_data["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
            secret_data["metadata"]["transfer_history"] = secret_data["metadata"].get("transfer_history", [])
            secret_data["metadata"]["transfer_history"].append(
                {
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                    "from_scope": secret_data.get("original_scope", "unknown"),
                    "to_scope": request.target_scope,
                    "from_chat_id": chat_id,
                    "to_chat_id": request.target_chat_id,
                }
            )

            secrets[secret_id] = secret_data
            transferred.append(secret_id)

        self._save_secrets(secrets)

        logger.info("Transferred %s secrets, %s failed", len(transferred), len(failed))
        return {
            "transferred": transferred,
            "failed": failed,
            "total_requested": len(request.secret_ids),
        }

    def cleanup_chat_secrets(self, chat_id: str) -> Metadata:
        """Clean up secrets when a chat is deleted"""
        secrets = self._load_secrets()
        chat_secrets = []

        # Find all secrets for this chat
        for secret_id, secret_data in secrets.items():
            if secret_data["scope"] == SecretScope.CHAT and secret_data["chat_id"] == chat_id:
                chat_secrets.append(
                    {
                        "id": secret_id,
                        "name": secret_data["name"],
                        "type": secret_data["type"],
                        "description": secret_data["description"],
                    }
                )

        return {
            "chat_id": chat_id,
            "secrets_found": chat_secrets,
            "total_count": len(chat_secrets),
        }

    def delete_chat_secrets(self, chat_id: str, secret_ids: List[str] | None = None) -> Metadata:
        """Delete specific or all secrets for a chat"""
        secrets = self._load_secrets()
        deleted = []

        for secret_id, secret_data in list(secrets.items()):
            if secret_data["scope"] == SecretScope.CHAT and secret_data["chat_id"] == chat_id:
                if secret_ids is None or secret_id in secret_ids:
                    del secrets[secret_id]
                    deleted.append({"id": secret_id, "name": secret_data["name"]})

        self._save_secrets(secrets)

        logger.info("Deleted %s secrets for chat %s", len(deleted), chat_id)
        return {
            "chat_id": chat_id,
            "deleted_secrets": deleted,
            "total_deleted": len(deleted),
        }


# Global secrets manager instance
secrets_manager = SecretsManager()


def get_client_id(request: Request) -> str:
    """Extract client identifier for rate limiting.

    Only trusts X-Forwarded-For when the direct TCP peer is a known
    reverse proxy (Issue #2252).  Delegates to get_client_ip().
    """
    return get_client_ip(request) or "unknown"


def check_rate_limit(request: Request) -> None:
    """Check rate limit and raise exception if exceeded"""
    client_id = get_client_id(request)
    if not rate_limiter.is_allowed(client_id):
        logger.warning("[Secrets] Rate limit exceeded for client: %s", client_id)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
        )


def audit_log(
    operation: str,
    secret_id: str,
    request: Request,
    success: bool = True,
    details: str = "",
) -> None:
    """Log security-relevant operations for audit trail"""
    client_id = get_client_id(request)
    status = "SUCCESS" if success else "FAILED"
    # Redact secret_id to prevent sensitive data in logs
    safe_id = secret_id[:8] + "..." if secret_id and len(secret_id) > 8 else secret_id
    logger.info(  # codeql[py/clear-text-logging-sensitive-data]
        "[Secrets Audit] %s | Operation: %s | " "SecretID: %s | Client: %s",
        status,
        operation,
        safe_id,  # codeql[py/clear-text-logging-sensitive-data]
        client_id,
    )


# API Endpoints


@router.post("/", response_model=DataResponse[SecretCreatedData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_secret",
    error_code_prefix="SECRETS",
)
async def create_secret(
    request: SecretCreateRequest,
    http_request: Request,
    admin_check: bool = Depends(check_admin_permission),
):
    """Create a new secret (Issue #744: requires admin authentication)"""
    check_rate_limit(http_request)
    try:
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        secret = await asyncio.to_thread(secrets_manager.create_secret, request)
        # Convert datetime objects to strings for JSON serialization
        secret_data = secret.dict()
        if secret_data.get("created_at"):
            secret_data["created_at"] = secret_data["created_at"].isoformat()
        if secret_data.get("updated_at"):
            secret_data["updated_at"] = secret_data["updated_at"].isoformat()
        if secret_data.get("expires_at"):
            secret_data["expires_at"] = secret_data["expires_at"].isoformat()

        audit_log("CREATE", secret.id, http_request, details=f"name={request.name}")
        _user = get_auth_middleware().get_user_from_request(http_request)
        audit_record(
            user_id=str((_user or {}).get("user_id", "unknown")),
            action=AuditAction.API_KEY_CREATE,
            resource_type="secret",
            resource_id=secret.id,
            ip_address=http_request.client.host if http_request.client else "unknown",
            session_id=None,
            outcome="success",
        )
        return JSONResponse(
            status_code=201,
            content={
                "status": "success",
                "message": "Secret created successfully",
                "secret": secret_data,
            },
        )
    except ValueError as e:
        audit_log("CREATE", "N/A", http_request, success=False, details=str(e))
        raise HTTPException(status_code=400, detail="Internal server error")
    except Exception as e:
        audit_log("CREATE", "N/A", http_request, success=False, details=str(e))
        logger.error("Failed to create secret: %s", e)  # codeql[py/clear-text-logging-sensitive-data]
        raise HTTPException(status_code=500, detail="Failed to create secret")


@router.get("/", response_model=DataResponse[SecretsListData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_secrets",
    error_code_prefix="SECRETS",
)
async def list_secrets(
    http_request: Request,
    chat_id: str | None = Query(None),
    scope: SecretScope | None = Query(None),
    admin_check: bool = Depends(check_admin_permission),
):
    """List secrets with optional filtering (Issue #744: requires admin authentication)"""
    check_rate_limit(http_request)
    try:
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        secrets = await asyncio.to_thread(secrets_manager.list_secrets, chat_id=chat_id, scope=scope)
        audit_log("LIST", "N/A", http_request, details=f"count={len(secrets)}")
        return JSONResponse(
            status_code=200,
            content={
                "secrets": secrets,
                "total_count": len(secrets),
                "filters": {"chat_id": chat_id, "scope": scope},
            },
        )
    except Exception as e:
        logger.error("Failed to list secrets: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list secrets")


@router.get("/types", response_model=DataResponse[SecretTypesData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_secret_types",
    error_code_prefix="SECRETS",
)
async def get_secret_types(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get available secret types (Issue #744: requires admin authentication)"""
    return JSONResponse(
        status_code=200,
        content={
            "types": [{"value": t.value, "label": t.value.replace("_", " ").title()} for t in SecretType],
            "scopes": [{"value": s.value, "label": s.value.title()} for s in SecretScope],
        },
    )


@router.get("/status", response_model=SecretsStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_secrets_status",
    error_code_prefix="SECRETS",
)
async def get_secrets_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get secrets service status (Issue #744: requires admin authentication)"""
    try:
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        secrets = await asyncio.to_thread(secrets_manager._load_secrets)

        return {
            "status": "healthy",
            "service": "secrets_manager",
            "total_secrets": len(secrets),
            "storage_backend": "file",
            "encryption_enabled": True,  # Fernet symmetric encryption is used
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Failed to get secrets status: %s", e)
        return {
            "status": "error",
            "service": "secrets_manager",
            "error": "Internal server error",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }


@router.get("/stats", response_model=DataResponse[SecretsStatsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_secrets_stats",
    error_code_prefix="SECRETS",
)
async def get_secrets_stats(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get secrets statistics (Issue #744: requires admin authentication)"""
    try:
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        secrets = await asyncio.to_thread(secrets_manager._load_secrets)

        stats = {
            "total_secrets": len(secrets),
            "by_scope": {"chat": 0, "general": 0},
            "by_type": {},
            "by_chat": {},
            "expired_count": 0,
        }

        now = datetime.now(tz=timezone.utc)

        for secret_data in secrets.values():
            # Count by scope
            stats["by_scope"][secret_data["scope"]] += 1

            # Count by type
            secret_type = secret_data["type"]
            stats["by_type"][secret_type] = stats["by_type"].get(secret_type, 0) + 1

            # Count by chat (for chat-scoped secrets)
            if secret_data["scope"] == "chat" and secret_data.get("chat_id"):
                chat_id = secret_data["chat_id"]
                stats["by_chat"][chat_id] = stats["by_chat"].get(chat_id, 0) + 1

            # Count expired secrets
            if secret_data.get("expires_at"):
                expires_at = parse_utc_iso(secret_data["expires_at"])
                if expires_at < now:
                    stats["expired_count"] += 1

        return JSONResponse(status_code=200, content=stats)
    except Exception as e:
        logger.error("Failed to get secrets stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get stats")


@router.get("/{secret_id}", response_model=DataResponse[SecretCreatedData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_secret",
    error_code_prefix="SECRETS",
)
async def get_secret(
    secret_id: str,
    http_request: Request,
    chat_id: str | None = Query(None),
    admin_check: bool = Depends(check_admin_permission),
):
    """Get a specific secret with its value (Issue #744: requires admin authentication)"""
    check_rate_limit(http_request)
    try:
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        secret = await asyncio.to_thread(secrets_manager.get_secret, secret_id, chat_id=chat_id)
        if not secret:
            audit_log("ACCESS", secret_id, http_request, success=False, details="not_found")
            raise HTTPException(status_code=404, detail="Secret not found")

        # Issue #608: Track secret usage in memory graph when accessed within a chat
        if chat_id:
            memory_graph: AutoBotMemoryGraph | None = getattr(http_request.app.state, "memory_graph", None)
            if memory_graph:
                try:
                    await memory_graph.create_secret_entity(
                        name=secret.get("name", secret_id),
                        secret_type=secret.get("type", "other"),
                        owner_id=secret.get("chat_id") or "system",
                        scope="session" if secret.get("scope") == "chat" else "user",
                        session_id=chat_id,
                        metadata={
                            "secret_id": secret_id[:8] + "...",
                            "accessed_via": "api",
                            "original_scope": secret.get("scope"),
                        },
                    )
                    logger.debug(  # codeql[py/clear-text-logging-sensitive-data]
                        "[Issue #608] Created secret entity for %s... in session %s",
                        secret_id[:8],
                        chat_id,
                    )
                except Exception as graph_err:
                    logger.warning("[Issue #608] Failed to create secret entity: %s", graph_err)

        audit_log("ACCESS", secret_id, http_request, details="value_retrieved")
        return JSONResponse(status_code=200, content=secret)
    except PermissionError:
        audit_log(
            "ACCESS",
            secret_id,
            http_request,
            success=False,
            details="permission_denied",
        )
        raise HTTPException(status_code=403, detail="Internal server error")
    except HTTPException:
        raise
    except Exception as e:
        audit_log("ACCESS", secret_id, http_request, success=False, details=str(e))
        logger.error("Failed to get secret: %s", e)  # codeql[py/clear-text-logging-sensitive-data]
        raise HTTPException(status_code=500, detail="Failed to get secret")


@router.put("/{secret_id}", response_model=DataResponse[SecretCreatedData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_secret",
    error_code_prefix="SECRETS",
)
async def update_secret(
    secret_id: str,
    request: SecretUpdateRequest,
    http_request: Request,
    chat_id: str | None = Query(None),
    admin_check: bool = Depends(check_admin_permission),
):
    """Update a secret's metadata (Issue #744: requires admin authentication)"""
    check_rate_limit(http_request)
    try:
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        secret = await asyncio.to_thread(secrets_manager.update_secret, secret_id, request, chat_id=chat_id)
        if not secret:
            audit_log("UPDATE", secret_id, http_request, success=False, details="not_found")
            raise HTTPException(status_code=404, detail="Secret not found")

        # Convert datetime objects to strings for JSON serialization
        secret_data = secret.dict()
        if secret_data.get("created_at"):
            secret_data["created_at"] = secret_data["created_at"].isoformat()
        if secret_data.get("updated_at"):
            secret_data["updated_at"] = secret_data["updated_at"].isoformat()
        if secret_data.get("expires_at"):
            secret_data["expires_at"] = secret_data["expires_at"].isoformat()

        audit_log("UPDATE", secret_id, http_request)
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Secret updated successfully",
                "secret": secret_data,
            },
        )
    except PermissionError:
        audit_log(
            "UPDATE",
            secret_id,
            http_request,
            success=False,
            details="permission_denied",
        )
        raise HTTPException(status_code=403, detail="Internal server error")
    except HTTPException:
        raise
    except Exception as e:
        audit_log("UPDATE", secret_id, http_request, success=False, details=str(e))
        logger.error("Failed to update secret: %s", e)  # codeql[py/clear-text-logging-sensitive-data]
        raise HTTPException(status_code=500, detail="Failed to update secret")


@router.delete("/{secret_id}", response_model=DataResponse[SecretCreatedData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_secret",
    error_code_prefix="SECRETS",
)
async def delete_secret(
    secret_id: str,
    http_request: Request,
    chat_id: str | None = Query(None),
    admin_check: bool = Depends(check_admin_permission),
):
    """Delete a secret (Issue #744: requires admin authentication)"""
    check_rate_limit(http_request)
    try:
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        success = await asyncio.to_thread(secrets_manager.delete_secret, secret_id, chat_id=chat_id)
        if not success:
            audit_log("DELETE", secret_id, http_request, success=False, details="not_found")
            raise HTTPException(status_code=404, detail="Secret not found")

        audit_log("DELETE", secret_id, http_request)
        _user = get_auth_middleware().get_user_from_request(http_request)
        audit_record(
            user_id=str((_user or {}).get("user_id", "unknown")),
            action=AuditAction.API_KEY_REVOKE,
            resource_type="secret",
            resource_id=secret_id,
            ip_address=http_request.client.host if http_request.client else "unknown",
            session_id=None,
            outcome="success",
        )
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Secret deleted successfully"},
        )
    except PermissionError:
        audit_log(
            "DELETE",
            secret_id,
            http_request,
            success=False,
            details="permission_denied",
        )
        raise HTTPException(status_code=403, detail="Internal server error")
    except HTTPException:
        raise
    except Exception as e:
        audit_log("DELETE", secret_id, http_request, success=False, details=str(e))
        logger.error("Failed to delete secret: %s", e)  # codeql[py/clear-text-logging-sensitive-data]
        raise HTTPException(status_code=500, detail="Failed to delete secret")


@router.post("/transfer", response_model=DataResponse[SecretTransferData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="transfer_secrets",
    error_code_prefix="SECRETS",
)
async def transfer_secrets(
    request: SecretTransferRequest,
    http_request: Request,
    chat_id: str | None = Query(None),
    admin_check: bool = Depends(check_admin_permission),
):
    """Transfer secrets between scopes (Issue #744: requires admin authentication)"""
    check_rate_limit(http_request)
    try:
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        result = await asyncio.to_thread(secrets_manager.transfer_secrets, request, chat_id=chat_id)
        audit_log(
            "TRANSFER",
            ",".join(result.get("transferred", [])),
            http_request,
            details=f"to={request.target_scope}",
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": (
                    f"Transfer completed: {result['total_requested']} requested, "
                    f"{len(result['transferred'])} transferred"
                ),
                "result": result,
            },
        )
    except Exception as e:
        audit_log("TRANSFER", "N/A", http_request, success=False, details=str(e))
        logger.error("Failed to transfer secrets: %s", e)
        raise HTTPException(status_code=500, detail="Failed to transfer secrets")


@router.get("/chat/{chat_id}/cleanup", response_model=DataResponse[ChatSecretsDeleteData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_chat_cleanup_info",
    error_code_prefix="SECRETS",
)
async def get_chat_cleanup_info(
    chat_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """Get information about secrets affected by chat deletion (Issue #744: requires admin auth)"""
    try:
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        info = await asyncio.to_thread(secrets_manager.cleanup_chat_secrets, chat_id)
        return JSONResponse(status_code=200, content=info)
    except Exception as e:
        logger.error("Failed to get chat cleanup info: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get cleanup info")


@router.delete("/chat/{chat_id}", response_model=DataResponse[ChatSecretsDeleteData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_chat_secrets",
    error_code_prefix="SECRETS",
)
async def delete_chat_secrets(
    chat_id: str,
    http_request: Request,
    secret_ids: List[str] | None = Query(None),
    admin_check: bool = Depends(check_admin_permission),
):
    """Delete secrets for a specific chat (Issue #744: requires admin authentication)"""
    check_rate_limit(http_request)
    try:
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        result = await asyncio.to_thread(secrets_manager.delete_chat_secrets, chat_id, secret_ids)
        deleted_ids = [s.get("id", "unknown") for s in result.get("deleted_secrets", [])]
        audit_log(
            "BULK_DELETE",
            ",".join(deleted_ids),
            http_request,
            details=f"chat={chat_id}, count={result['total_deleted']}",
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": (f"Deleted {result['total_deleted']} secrets for chat {chat_id}"),
                "result": result,
            },
        )
    except Exception as e:
        audit_log("BULK_DELETE", "N/A", http_request, success=False, details=str(e))
        logger.error("Failed to delete chat secrets: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete chat secrets")
