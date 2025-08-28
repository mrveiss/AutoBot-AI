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

import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet
import base64
import os

logger = logging.getLogger(__name__)

router = APIRouter()


class SecretScope(str, Enum):
    """Secret scope enumeration"""

    CHAT = "chat"
    GENERAL = "general"


class SecretType(str, Enum):
    """Secret type enumeration"""

    SSH_KEY = "ssh_key"
    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    CERTIFICATE = "certificate"
    DATABASE_URL = "database_url"
    OTHER = "other"


class SecretModel(BaseModel):
    """Secret data model"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: SecretType
    scope: SecretScope
    chat_id: Optional[str] = None
    description: Optional[str] = ""
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SecretCreateRequest(BaseModel):
    """Request model for creating secrets"""

    name: str
    type: SecretType
    scope: SecretScope
    value: str
    chat_id: Optional[str] = None
    description: Optional[str] = ""
    tags: List[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SecretUpdateRequest(BaseModel):
    """Request model for updating secrets"""

    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class SecretTransferRequest(BaseModel):
    """Request model for transferring secrets between scopes"""

    secret_ids: List[str]
    target_scope: SecretScope
    target_chat_id: Optional[str] = None


class SecretsManager:
    """Manages encrypted secrets with dual scope support"""

    def __init__(self):
        self.secrets_file = "data/secrets.json"
        self.key_file = "data/secrets.key"
        self._ensure_directories()
        self._initialize_encryption()

    def _ensure_directories(self):
        """Ensure data directory exists"""
        os.makedirs("data", exist_ok=True)

    def _initialize_encryption(self):
        """Initialize or load encryption key"""
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(key)
            os.chmod(self.key_file, 0o600)  # Restrict permissions

        self.cipher = Fernet(key)

    def _encrypt_value(self, value: str) -> str:
        """Encrypt a secret value"""
        return base64.b64encode(self.cipher.encrypt(value.encode())).decode()

    def _decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a secret value"""
        return self.cipher.decrypt(base64.b64decode(encrypted_value.encode())).decode()

    def _load_secrets(self) -> Dict[str, Dict]:
        """Load secrets from encrypted storage"""
        if not os.path.exists(self.secrets_file):
            return {}

        try:
            with open(self.secrets_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logger.warning("Secrets file corrupted or missing, initializing empty")
            return {}

    def _save_secrets(self, secrets: Dict[str, Dict]):
        """Save secrets to encrypted storage"""

        def json_serializer(obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return str(obj)

        with open(self.secrets_file, "w") as f:
            json.dump(secrets, f, indent=2, default=json_serializer)
        os.chmod(self.secrets_file, 0o600)  # Restrict permissions

    def create_secret(self, request: SecretCreateRequest) -> SecretModel:
        """Create a new secret"""
        secrets = self._load_secrets()

        # Validate scope and chat_id consistency
        if request.scope == SecretScope.CHAT and not request.chat_id:
            raise ValueError("Chat-scoped secrets must have a chat_id")
        if request.scope == SecretScope.GENERAL and request.chat_id:
            request.chat_id = None  # Clear chat_id for general secrets

        # Create secret model
        secret = SecretModel(
            name=request.name,
            type=request.type,
            scope=request.scope,
            chat_id=request.chat_id,
            description=request.description,
            tags=request.tags,
            expires_at=request.expires_at,
            metadata=request.metadata,
        )

        # Encrypt and store the secret value
        encrypted_value = self._encrypt_value(request.value)
        secret_data = secret.dict()
        secret_data["encrypted_value"] = encrypted_value

        secrets[secret.id] = secret_data
        self._save_secrets(secrets)

        logger.info(
            f"Created {request.scope} secret '{request.name}' (ID: {secret.id})"
        )
        return secret

    def get_secret(
        self, secret_id: str, chat_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Get a secret with access control"""
        secrets = self._load_secrets()
        secret_data = secrets.get(secret_id)

        if not secret_data:
            return None

        # Check access permissions
        if secret_data["scope"] == SecretScope.CHAT:
            if not chat_id or secret_data["chat_id"] != chat_id:
                raise PermissionError(
                    "Access denied: Chat-scoped secret from different chat"
                )

        # Return secret with decrypted value
        secret_data = secret_data.copy()
        secret_data["value"] = self._decrypt_value(secret_data["encrypted_value"])
        del secret_data["encrypted_value"]

        return secret_data

    def list_secrets(
        self, chat_id: Optional[str] = None, scope: Optional[SecretScope] = None
    ) -> List[Dict]:
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
        chat_id: Optional[str] = None,
    ) -> Optional[SecretModel]:
        """Update a secret with access control"""
        secrets = self._load_secrets()
        secret_data = secrets.get(secret_id)

        if not secret_data:
            return None

        # Check access permissions
        if secret_data["scope"] == SecretScope.CHAT:
            if not chat_id or secret_data["chat_id"] != chat_id:
                raise PermissionError(
                    "Access denied: Cannot modify chat-scoped secret from "
                    "different chat"
                )

        # Update fields
        if request.name is not None:
            secret_data["name"] = request.name
        if request.description is not None:
            secret_data["description"] = request.description
        if request.tags is not None:
            secret_data["tags"] = request.tags
        if request.expires_at is not None:
            secret_data["expires_at"] = (
                request.expires_at.isoformat() if request.expires_at else None
            )
        if request.metadata is not None:
            secret_data["metadata"] = request.metadata

        secret_data["updated_at"] = datetime.now().isoformat()

        secrets[secret_id] = secret_data
        self._save_secrets(secrets)

        logger.info(f"Updated secret '{secret_data['name']}' (ID: {secret_id})")

        # Return updated secret model
        safe_data = secret_data.copy()
        del safe_data["encrypted_value"]
        return SecretModel(**safe_data)

    def delete_secret(self, secret_id: str, chat_id: Optional[str] = None) -> bool:
        """Delete a secret with access control"""
        secrets = self._load_secrets()
        secret_data = secrets.get(secret_id)

        if not secret_data:
            return False

        # Check access permissions
        if secret_data["scope"] == SecretScope.CHAT:
            if not chat_id or secret_data["chat_id"] != chat_id:
                raise PermissionError(
                    "Access denied: Cannot delete chat-scoped secret from "
                    "different chat"
                )

        del secrets[secret_id]
        self._save_secrets(secrets)

        logger.info(f"Deleted secret '{secret_data['name']}' (ID: {secret_id})")
        return True

    def transfer_secrets(
        self, request: SecretTransferRequest, chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
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

            secret_data["updated_at"] = datetime.now().isoformat()
            secret_data["metadata"]["transfer_history"] = secret_data["metadata"].get(
                "transfer_history", []
            )
            secret_data["metadata"]["transfer_history"].append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "from_scope": secret_data.get("original_scope", "unknown"),
                    "to_scope": request.target_scope,
                    "from_chat_id": chat_id,
                    "to_chat_id": request.target_chat_id,
                }
            )

            secrets[secret_id] = secret_data
            transferred.append(secret_id)

        self._save_secrets(secrets)

        logger.info(f"Transferred {len(transferred)} secrets, {len(failed)} failed")
        return {
            "transferred": transferred,
            "failed": failed,
            "total_requested": len(request.secret_ids),
        }

    def cleanup_chat_secrets(self, chat_id: str) -> Dict[str, Any]:
        """Clean up secrets when a chat is deleted"""
        secrets = self._load_secrets()
        chat_secrets = []

        # Find all secrets for this chat
        for secret_id, secret_data in secrets.items():
            if (
                secret_data["scope"] == SecretScope.CHAT
                and secret_data["chat_id"] == chat_id
            ):
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

    def delete_chat_secrets(
        self, chat_id: str, secret_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Delete specific or all secrets for a chat"""
        secrets = self._load_secrets()
        deleted = []

        for secret_id, secret_data in list(secrets.items()):
            if (
                secret_data["scope"] == SecretScope.CHAT
                and secret_data["chat_id"] == chat_id
            ):
                if secret_ids is None or secret_id in secret_ids:
                    del secrets[secret_id]
                    deleted.append({"id": secret_id, "name": secret_data["name"]})

        self._save_secrets(secrets)

        logger.info(f"Deleted {len(deleted)} secrets for chat {chat_id}")
        return {
            "chat_id": chat_id,
            "deleted_secrets": deleted,
            "total_deleted": len(deleted),
        }


# Global secrets manager instance
secrets_manager = SecretsManager()


# API Endpoints


@router.post("/secrets")
async def create_secret(request: SecretCreateRequest):
    """Create a new secret"""
    try:
        secret = secrets_manager.create_secret(request)
        # Convert datetime objects to strings for JSON serialization
        secret_data = secret.dict()
        if secret_data.get("created_at"):
            secret_data["created_at"] = secret_data["created_at"].isoformat()
        if secret_data.get("updated_at"):
            secret_data["updated_at"] = secret_data["updated_at"].isoformat()
        if secret_data.get("expires_at"):
            secret_data["expires_at"] = secret_data["expires_at"].isoformat()

        return JSONResponse(
            status_code=201,
            content={
                "status": "success",
                "message": "Secret created successfully",
                "secret": secret_data,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create secret: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create secret: {str(e)}"
        )


@router.get("/secrets")
async def list_secrets(
    chat_id: Optional[str] = Query(None), scope: Optional[SecretScope] = Query(None)
):
    """List secrets with optional filtering"""
    try:
        secrets = secrets_manager.list_secrets(chat_id=chat_id, scope=scope)
        return JSONResponse(
            status_code=200,
            content={
                "secrets": secrets,
                "total_count": len(secrets),
                "filters": {"chat_id": chat_id, "scope": scope},
            },
        )
    except Exception as e:
        logger.error(f"Failed to list secrets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list secrets: {str(e)}")


@router.get("/secrets/{secret_id}")
async def get_secret(secret_id: str, chat_id: Optional[str] = Query(None)):
    """Get a specific secret with its value"""
    try:
        secret = secrets_manager.get_secret(secret_id, chat_id=chat_id)
        if not secret:
            raise HTTPException(status_code=404, detail="Secret not found")

        return JSONResponse(status_code=200, content=secret)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get secret: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get secret: {str(e)}")


@router.put("/secrets/{secret_id}")
async def update_secret(
    secret_id: str, request: SecretUpdateRequest, chat_id: Optional[str] = Query(None)
):
    """Update a secret's metadata"""
    try:
        secret = secrets_manager.update_secret(secret_id, request, chat_id=chat_id)
        if not secret:
            raise HTTPException(status_code=404, detail="Secret not found")

        # Convert datetime objects to strings for JSON serialization
        secret_data = secret.dict()
        if secret_data.get("created_at"):
            secret_data["created_at"] = secret_data["created_at"].isoformat()
        if secret_data.get("updated_at"):
            secret_data["updated_at"] = secret_data["updated_at"].isoformat()
        if secret_data.get("expires_at"):
            secret_data["expires_at"] = secret_data["expires_at"].isoformat()

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Secret updated successfully",
                "secret": secret_data,
            },
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update secret: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to update secret: {str(e)}"
        )


@router.delete("/secrets/{secret_id}")
async def delete_secret(secret_id: str, chat_id: Optional[str] = Query(None)):
    """Delete a secret"""
    try:
        success = secrets_manager.delete_secret(secret_id, chat_id=chat_id)
        if not success:
            raise HTTPException(status_code=404, detail="Secret not found")

        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Secret deleted successfully"},
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete secret: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete secret: {str(e)}"
        )


@router.post("/secrets/transfer")
async def transfer_secrets(
    request: SecretTransferRequest, chat_id: Optional[str] = Query(None)
):
    """Transfer secrets between scopes"""
    try:
        result = secrets_manager.transfer_secrets(request, chat_id=chat_id)
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
        logger.error(f"Failed to transfer secrets: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to transfer secrets: {str(e)}"
        )


@router.get("/secrets/chat/{chat_id}/cleanup")
async def get_chat_cleanup_info(chat_id: str):
    """Get information about secrets that would be affected by chat deletion"""
    try:
        info = secrets_manager.cleanup_chat_secrets(chat_id)
        return JSONResponse(status_code=200, content=info)
    except Exception as e:
        logger.error(f"Failed to get chat cleanup info: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get cleanup info: {str(e)}"
        )


@router.delete("/secrets/chat/{chat_id}")
async def delete_chat_secrets(
    chat_id: str, secret_ids: Optional[List[str]] = Query(None)
):
    """Delete secrets for a specific chat (used during chat cleanup)"""
    try:
        result = secrets_manager.delete_chat_secrets(chat_id, secret_ids)
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": (
                    f"Deleted {result['total_deleted']} secrets for chat {chat_id}"
                ),
                "result": result,
            },
        )
    except Exception as e:
        logger.error(f"Failed to delete chat secrets: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete chat secrets: {str(e)}"
        )


@router.get("/secrets/types")
async def get_secret_types():
    """Get available secret types"""
    return JSONResponse(
        status_code=200,
        content={
            "types": [
                {"value": t.value, "label": t.value.replace("_", " ").title()}
                for t in SecretType
            ],
            "scopes": [
                {"value": s.value, "label": s.value.title()} for s in SecretScope
            ],
        },
    )


@router.get("/secrets/stats")
async def get_secrets_stats():
    """Get secrets statistics"""
    try:
        secrets = secrets_manager._load_secrets()

        stats = {
            "total_secrets": len(secrets),
            "by_scope": {"chat": 0, "general": 0},
            "by_type": {},
            "by_chat": {},
            "expired_count": 0,
        }

        now = datetime.now()

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
                expires_at = datetime.fromisoformat(secret_data["expires_at"])
                if expires_at < now:
                    stats["expired_count"] += 1

        return JSONResponse(status_code=200, content=stats)
    except Exception as e:
        logger.error(f"Failed to get secrets stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")
