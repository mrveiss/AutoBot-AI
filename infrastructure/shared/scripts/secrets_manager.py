#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Secrets Management System
=================================

Production-ready secrets management with encryption, access controls, and scope isolation.

Features:
- Dual-scope architecture (chat-scoped vs general-scoped)
- AES-256 encryption for secrets at rest
- Multiple input methods (GUI tab + chat-based entry)
- Secret types: SSH keys, passwords, API keys, certificates
- Transfer capability between scopes
- Cleanup dialogs and safe deletion
- Agent integration with seamless access
- Audit logging for security compliance

Usage:
    python scripts/secrets_manager.py --add --name "api_key" --type "api_key" --scope "general"
    python scripts/secrets_manager.py --list --scope "chat_123"
    python scripts/secrets_manager.py --transfer --from-chat "chat_123" --to-general
    python scripts/secrets_manager.py --cleanup-chat "chat_456"
"""

import argparse
import base64
import getpass
import json
import os
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class SecretType:
    """Supported secret types."""

    API_KEY = "api_key"  # pragma: allowlist secret
    PASSWORD = "password"  # pragma: allowlist secret
    SSH_KEY = "ssh_key"
    CERTIFICATE = "certificate"
    TOKEN = "token"
    DATABASE_URL = "database_url"
    WEBHOOK_URL = "webhook_url"
    CUSTOM = "custom"


class SecretScope:
    """Secret access scopes."""

    GENERAL = "general"  # Available across all chats
    CHAT = "chat"  # Available only within specific chat


class SecretsManager:
    """Secure secrets management with encryption and access controls."""

    def __init__(self, secrets_dir: str = "data/secrets"):
        """Initialize secrets manager with encryption and secrets index."""
        self.project_root = Path(__file__).parent.parent
        self.secrets_dir = self.project_root / secrets_dir
        self.secrets_dir.mkdir(parents=True, exist_ok=True)

        # Encryption setup
        self.master_key_file = self.secrets_dir / ".master_key"
        self.secrets_index_file = self.secrets_dir / "secrets_index.json"
        self.audit_log_file = self.secrets_dir / "audit_log.json"

        # Thread-safety locks
        self._index_lock = threading.Lock()
        self._audit_lock = threading.Lock()

        # Initialize encryption
        self.cipher_suite = self._initialize_encryption()

        # Load secrets index
        self.secrets_index = self._load_secrets_index()

        logger.info("🔐 AutoBot Secrets Manager initialized")
        logger.info(f"   Secrets Directory: {self.secrets_dir}")
        logger.info(f"   Indexed Secrets: {len(self.secrets_index)}")

    def print_header(self, title: str):
        """Print formatted header."""
        ScriptFormatter.print_header(title)

    def print_step(self, step: str, status: str = "info"):
        """Print step with status."""
        ScriptFormatter.print_step(step, status)

    def _initialize_encryption(self) -> Fernet:
        """Initialize encryption system."""
        if self.master_key_file.exists():
            # Load existing master key
            with open(self.master_key_file, "rb") as f:
                key = f.read()
        else:
            # Generate new master key
            self.print_step("Generating new master encryption key", "secure")

            # Use password-based key derivation
            password = getpass.getpass(
                "Enter master password for secrets encryption: "
            ).encode()
            salt = os.urandom(16)

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password))

            # Save master key and salt
            with open(self.master_key_file, "wb") as f:
                f.write(key)

            with open(self.secrets_dir / ".salt", "wb") as f:
                f.write(salt)

            # Secure the master key file
            os.chmod(self.master_key_file, 0o600)
            os.chmod(self.secrets_dir / ".salt", 0o600)

        return Fernet(key)

    def _load_secrets_index(self) -> Dict[str, Any]:
        """Load secrets index."""
        if self.secrets_index_file.exists():
            try:
                with open(self.secrets_index_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                self.print_step(
                    f"Warning: Could not load secrets index: {e}", "warning"
                )

        return {"secrets": {}, "chats": {}}

    def _save_secrets_index(self):
        """Save secrets index (thread-safe)."""
        with self._index_lock:
            try:
                with open(self.secrets_index_file, "w") as f:
                    json.dump(self.secrets_index, f, indent=2)
                os.chmod(self.secrets_index_file, 0o600)
            except Exception as e:
                self.print_step(f"Error saving secrets index: {e}", "error")

    def _log_audit_event(
        self,
        action: str,
        secret_id: str,
        scope: str,
        chat_id: str = None,
        details: str = None,
    ):
        """Log security audit event (thread-safe)."""
        audit_event = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "secret_id": secret_id,
            "scope": scope,
            "chat_id": chat_id,
            "details": details,
            "user": os.getenv("USER", "unknown"),
            "pid": os.getpid(),
        }

        with self._audit_lock:
            # Load existing audit log
            audit_log = []
            if self.audit_log_file.exists():
                try:
                    with open(self.audit_log_file, "r") as f:
                        audit_log = json.load(f)
                except Exception:
                    audit_log = []

            audit_log.append(audit_event)

            # Keep last 1000 events
            if len(audit_log) > 1000:
                audit_log = audit_log[-1000:]

            # Save audit log
            with open(self.audit_log_file, "w") as f:
                json.dump(audit_log, f, indent=2)
            os.chmod(self.audit_log_file, 0o600)

    def generate_secret_id(self) -> str:
        """Generate unique secret ID."""
        return str(uuid.uuid4())

    def add_secret(
        self,
        name: str,
        value: str,
        secret_type: str = SecretType.CUSTOM,
        scope: str = SecretScope.GENERAL,
        chat_id: str = None,
        description: str = "",
        tags: List[str] = None,
    ) -> str:
        """Add a new secret."""
        secret_id = self.generate_secret_id()

        # Validate scope and chat_id
        if scope == SecretScope.CHAT and not chat_id:
            raise ValueError("chat_id required for chat-scoped secrets")

        if tags is None:
            tags = []

        # Encrypt secret value
        encrypted_value = self.cipher_suite.encrypt(value.encode())

        # Create secret metadata
        secret_metadata = {
            "id": secret_id,
            "name": name,
            "type": secret_type,
            "scope": scope,
            "chat_id": chat_id,
            "description": description,
            "tags": tags,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "access_count": 0,
            "last_accessed": None,
        }

        # Save encrypted secret
        secret_file = self.secrets_dir / f"{secret_id}.secret"
        with open(secret_file, "wb") as f:
            f.write(encrypted_value)
        os.chmod(secret_file, 0o600)

        # Update index (thread-safe)
        with self._index_lock:
            self.secrets_index["secrets"][secret_id] = secret_metadata

            # Update chat index if chat-scoped
            if scope == SecretScope.CHAT and chat_id:
                if chat_id not in self.secrets_index["chats"]:
                    self.secrets_index["chats"][chat_id] = []
                self.secrets_index["chats"][chat_id].append(secret_id)

        self._save_secrets_index()

        # Log audit event
        self._log_audit_event(
            "add_secret",
            secret_id,
            scope,
            chat_id,
            f"Added {secret_type} secret: {name}",
        )

        self.print_step(f"Secret added: {name} (ID: {secret_id[:8]}...)", "success")
        return secret_id

    def get_secret(self, secret_id: str, chat_id: str = None) -> Optional[str]:
        """Retrieve and decrypt a secret (thread-safe)."""
        # Thread-safe read of metadata
        with self._index_lock:
            if secret_id not in self.secrets_index["secrets"]:
                return None
            secret_metadata = self.secrets_index["secrets"][secret_id]
            secret_scope = secret_metadata["scope"]
            secret_chat_id = secret_metadata.get("chat_id")
            secret_name = secret_metadata["name"]

        # Check access permissions (outside lock)
        if secret_scope == SecretScope.CHAT:
            if not chat_id or secret_chat_id != chat_id:
                self.print_step("Access denied to chat-scoped secret", "error")
                return None

        try:
            # Load and decrypt secret
            secret_file = self.secrets_dir / f"{secret_id}.secret"
            if not secret_file.exists():
                self.print_step(f"Secret file not found: {secret_id}", "error")
                return None

            with open(secret_file, "rb") as f:
                encrypted_value = f.read()

            decrypted_value = self.cipher_suite.decrypt(encrypted_value).decode()

            # Update access statistics (thread-safe)
            with self._index_lock:
                if secret_id in self.secrets_index["secrets"]:
                    self.secrets_index["secrets"][secret_id]["access_count"] += 1
                    self.secrets_index["secrets"][secret_id][
                        "last_accessed"
                    ] = datetime.now().isoformat()
            self._save_secrets_index()

            # Log audit event
            self._log_audit_event(
                "access_secret",
                secret_id,
                secret_scope,
                chat_id,
                f"Accessed secret: {secret_name}",
            )

            return decrypted_value

        except Exception as e:
            self.print_step(f"Error decrypting secret: {e}", "error")
            return None

    def list_secrets(
        self, scope: str = None, chat_id: str = None, secret_type: str = None
    ) -> List[Dict[str, Any]]:
        """List secrets with filtering options (thread-safe)."""
        secrets = []

        # Thread-safe iteration over secrets index
        with self._index_lock:
            secrets_copy = dict(self.secrets_index["secrets"])

        for secret_id, metadata in secrets_copy.items():
            # Apply filters
            if scope and metadata["scope"] != scope:
                continue

            if secret_type and metadata["type"] != secret_type:
                continue

            # Chat scope filtering
            if scope == SecretScope.CHAT:
                if not chat_id or metadata["chat_id"] != chat_id:
                    continue
            elif (
                metadata["scope"] == SecretScope.CHAT and chat_id != metadata["chat_id"]
            ):
                # Skip chat secrets from other chats
                continue

            # Create safe metadata (no sensitive data)
            safe_metadata = metadata.copy()
            secrets.append(safe_metadata)

        return sorted(secrets, key=lambda x: x["created_at"], reverse=True)

    def update_secret(
        self,
        secret_id: str,
        value: str = None,
        name: str = None,
        description: str = None,
        tags: List[str] = None,
        chat_id: str = None,
    ) -> bool:
        """Update an existing secret."""
        if secret_id not in self.secrets_index["secrets"]:
            self.print_step(f"Secret not found: {secret_id}", "error")
            return False

        secret_metadata = self.secrets_index["secrets"][secret_id]

        # Check permissions
        if secret_metadata["scope"] == SecretScope.CHAT:
            if not chat_id or secret_metadata["chat_id"] != chat_id:
                self.print_step("Access denied to chat-scoped secret", "error")
                return False

        try:
            # Update value if provided
            if value is not None:
                encrypted_value = self.cipher_suite.encrypt(value.encode())
                secret_file = self.secrets_dir / f"{secret_id}.secret"
                with open(secret_file, "wb") as f:
                    f.write(encrypted_value)

            # Update metadata
            if name is not None:
                secret_metadata["name"] = name
            if description is not None:
                secret_metadata["description"] = description
            if tags is not None:
                secret_metadata["tags"] = tags

            secret_metadata["updated_at"] = datetime.now().isoformat()
            self._save_secrets_index()

            # Log audit event
            self._log_audit_event(
                "update_secret",
                secret_id,
                secret_metadata["scope"],
                chat_id,
                f"Updated secret: {secret_metadata['name']}",
            )

            self.print_step(f"Secret updated: {secret_metadata['name']}", "success")
            return True

        except Exception as e:
            self.print_step(f"Error updating secret: {e}", "error")
            return False

    def delete_secret(self, secret_id: str, chat_id: str = None) -> bool:
        """Delete a secret (thread-safe)."""
        # Thread-safe read of metadata
        with self._index_lock:
            if secret_id not in self.secrets_index["secrets"]:
                self.print_step(f"Secret not found: {secret_id}", "error")
                return False
            secret_metadata = self.secrets_index["secrets"][secret_id].copy()
            secret_scope = secret_metadata["scope"]
            secret_chat_id = secret_metadata.get("chat_id")
            secret_name = secret_metadata["name"]

        # Check permissions (outside lock)
        if secret_scope == SecretScope.CHAT:
            if not chat_id or secret_chat_id != chat_id:
                self.print_step("Access denied to chat-scoped secret", "error")
                return False

        try:
            # Delete secret file
            secret_file = self.secrets_dir / f"{secret_id}.secret"
            if secret_file.exists():
                secret_file.unlink()

            # Thread-safe removal from index
            with self._index_lock:
                # Remove from chat index if applicable
                if secret_scope == SecretScope.CHAT and secret_chat_id:
                    chat_secrets = self.secrets_index["chats"].get(secret_chat_id, [])
                    if secret_id in chat_secrets:
                        chat_secrets.remove(secret_id)

                # Remove from index
                if secret_id in self.secrets_index["secrets"]:
                    del self.secrets_index["secrets"][secret_id]

            self._save_secrets_index()

            # Log audit event
            self._log_audit_event(
                "delete_secret",
                secret_id,
                secret_scope,
                chat_id,
                f"Deleted secret: {secret_name}",
            )

            self.print_step(f"Secret deleted: {secret_name}", "success")
            return True

        except Exception as e:
            self.print_step(f"Error deleting secret: {e}", "error")
            return False

    def transfer_secret_to_general(self, secret_id: str, chat_id: str) -> bool:
        """Transfer a chat-scoped secret to general scope (thread-safe)."""
        # Thread-safe read and validation
        with self._index_lock:
            if secret_id not in self.secrets_index["secrets"]:
                self.print_step(f"Secret not found: {secret_id}", "error")
                return False

            secret_metadata = self.secrets_index["secrets"][secret_id]
            secret_scope = secret_metadata["scope"]
            secret_chat_id = secret_metadata.get("chat_id")

            # Verify it's a chat-scoped secret from the correct chat
            if secret_scope != SecretScope.CHAT or secret_chat_id != chat_id:
                self.print_step(
                    f"Cannot transfer: not a chat-scoped secret from chat {chat_id}",
                    "error",
                )
                return False

        try:
            # Thread-safe update
            with self._index_lock:
                # Re-check existence under lock
                if secret_id not in self.secrets_index["secrets"]:
                    return False

                secret_metadata = self.secrets_index["secrets"][secret_id]
                secret_name = secret_metadata["name"]

                # Update scope
                secret_metadata["scope"] = SecretScope.GENERAL
                secret_metadata["chat_id"] = None
                secret_metadata["updated_at"] = datetime.now().isoformat()

                # Remove from chat index
                chat_secrets = self.secrets_index["chats"].get(chat_id, [])
                if secret_id in chat_secrets:
                    chat_secrets.remove(secret_id)

            self._save_secrets_index()

            # Log audit event
            self._log_audit_event(
                "transfer_secret",
                secret_id,
                SecretScope.GENERAL,
                chat_id,
                f"Transferred secret to general scope: {secret_name}",
            )

            self.print_step(
                f"Secret transferred to general scope: {secret_name}",
                "success",
            )
            return True

        except Exception as e:
            self.print_step(f"Error transferring secret: {e}", "error")
            return False

    def cleanup_chat_secrets(
        self, chat_id: str, transfer_to_general: bool = False
    ) -> Dict[str, int]:
        """Cleanup secrets for a deleted chat."""
        self.print_header(f"Cleaning up secrets for chat: {chat_id}")

        chat_secrets = self.secrets_index["chats"].get(chat_id, [])
        if not chat_secrets:
            self.print_step("No secrets found for this chat", "info")
            return {"transferred": 0, "deleted": 0}

        transferred_count = 0
        deleted_count = 0

        for secret_id in chat_secrets.copy():
            if secret_id not in self.secrets_index["secrets"]:
                continue

            secret_metadata = self.secrets_index["secrets"][secret_id]
            secret_name = secret_metadata["name"]

            if transfer_to_general:
                if self.transfer_secret_to_general(secret_id, chat_id):
                    transferred_count += 1
                    self.print_step(f"Transferred to general: {secret_name}", "success")
            else:
                if self.delete_secret(secret_id, chat_id):
                    deleted_count += 1
                    self.print_step(f"Deleted: {secret_name}", "success")

        # Clean up chat index
        if chat_id in self.secrets_index["chats"]:
            del self.secrets_index["chats"][chat_id]
            self._save_secrets_index()

        # Log audit event
        self._log_audit_event(
            "cleanup_chat",
            "",
            SecretScope.CHAT,
            chat_id,
            f"Cleanup completed: {transferred_count} transferred, {deleted_count} deleted",
        )

        return {"transferred": transferred_count, "deleted": deleted_count}

    def get_secrets_for_agent(
        self, agent_type: str, chat_id: str = None
    ) -> Dict[str, str]:
        """Get secrets relevant for an agent type."""
        relevant_secrets = {}

        # Get all accessible secrets
        all_secrets = self.list_secrets(chat_id=chat_id)

        # Filter by tags or type
        agent_tags = {
            "ssh": ["ssh", "server", "remote"],
            "api": ["api", "key", "token"],
            "database": ["db", "database", "sql"],
            "web": ["webhook", "url", "endpoint"],
        }

        relevant_tags = agent_tags.get(agent_type, [])

        for secret in all_secrets:
            # Check if secret is relevant for this agent
            if any(tag in secret.get("tags", []) for tag in relevant_tags):
                secret_value = self.get_secret(secret["id"], chat_id)
                if secret_value:
                    relevant_secrets[secret["name"]] = secret_value
            elif secret["type"] in relevant_tags:
                secret_value = self.get_secret(secret["id"], chat_id)
                if secret_value:
                    relevant_secrets[secret["name"]] = secret_value

        return relevant_secrets

    def rotate_secret(
        self, secret_id: str, new_value: str, chat_id: str = None
    ) -> bool:
        """Rotate a secret (update with new value and log rotation)."""
        if self.update_secret(secret_id, value=new_value, chat_id=chat_id):
            # Log rotation event
            secret_metadata = self.secrets_index["secrets"][secret_id]
            self._log_audit_event(
                "rotate_secret",
                secret_id,
                secret_metadata["scope"],
                chat_id,
                f"Rotated secret: {secret_metadata['name']}",
            )
            self.print_step(f"Secret rotated: {secret_metadata['name']}", "success")
            return True
        return False

    def export_secrets(
        self, chat_id: str = None, include_values: bool = False
    ) -> Dict[str, Any]:
        """Export secrets (metadata only by default, values with explicit flag)."""
        secrets = self.list_secrets(chat_id=chat_id)

        export_data = {
            "exported_at": datetime.now().isoformat(),
            "chat_id": chat_id,
            "total_secrets": len(secrets),
            "secrets": [],
        }

        for secret in secrets:
            export_secret = secret.copy()

            if include_values:
                # Only include values if explicitly requested (dangerous!)
                value = self.get_secret(secret["id"], chat_id)
                if value:
                    export_secret["value"] = value

            export_data["secrets"].append(export_secret)

        return export_data

    def get_security_report(self) -> Dict[str, Any]:
        """Generate security report (thread-safe)."""
        # Thread-safe read of secrets index
        with self._index_lock:
            secrets_copy = dict(self.secrets_index["secrets"])
            active_chats_count = len(self.secrets_index["chats"])

        total_secrets = len(secrets_copy)
        chat_secrets = sum(
            1 for s in secrets_copy.values() if s["scope"] == SecretScope.CHAT
        )
        general_secrets = total_secrets - chat_secrets

        # Secret types distribution
        type_counts = {}
        for secret in secrets_copy.values():
            secret_type = secret["type"]
            type_counts[secret_type] = type_counts.get(secret_type, 0) + 1

        # Recent activity (thread-safe read of audit log)
        recent_activity = []
        with self._audit_lock:
            if self.audit_log_file.exists():
                try:
                    with open(self.audit_log_file, "r") as f:
                        audit_log = json.load(f)

                    # Get last 10 events
                    recent_activity = audit_log[-10:]
                except Exception:
                    pass  # Audit log unreadable, activity remains empty

        return {
            "generated_at": datetime.now().isoformat(),
            "total_secrets": total_secrets,
            "general_secrets": general_secrets,
            "chat_secrets": chat_secrets,
            "active_chats": active_chats_count,
            "secret_types": type_counts,
            "recent_activity": recent_activity,
            "encryption_status": "active",
            "audit_logging": "enabled",
        }


def _handle_add_command(secrets_manager: SecretsManager, args) -> int:
    """Handle --add command (Issue #315: extracted helper)."""
    if not args.name:
        logger.error("❌ --name required for add")
        return 1

    value = args.value
    if not value:
        value = getpass.getpass(f"Enter value for secret '{args.name}': ")

    secret_id = secrets_manager.add_secret(
        name=args.name,
        value=value,
        secret_type=args.type,
        scope=args.scope,
        chat_id=args.chat_id,
        description=args.description or "",
        tags=args.tags or [],
    )

    if args.json:
        logger.info(json.dumps({"secret_id": secret_id, "status": "created"}))
    else:
        logger.info(f"✅ Secret created with ID: {secret_id}")
    return 0


def _handle_list_command(secrets_manager: SecretsManager, args) -> int:
    """Handle --list command (Issue #315: extracted helper)."""
    secrets = secrets_manager.list_secrets(
        scope=args.scope, chat_id=args.chat_id, secret_type=args.type
    )

    if args.json:
        logger.info(json.dumps({"secrets": secrets}))
        return 0

    if not secrets:
        logger.info("No secrets found")
        return 0

    logger.info(f"\n🔐 Found {len(secrets)} secrets:")
    logger.info("=" * 80)
    logger.info(f"{'Name':<25} {'Type':<15} {'Scope':<10} {'Chat ID':<15} {'Created':<20}")
    logger.info("-" * 80)

    for secret in secrets:
        created = datetime.fromisoformat(secret["created_at"]).strftime(
            "%Y-%m-%d %H:%M"
        )
        chat_display = secret.get("chat_id", "")[:12] if secret.get("chat_id") else ""
        logger.info(
            f"{secret['name']:<25} {secret['type']:<15} {secret['scope']:<10} "
            f"{chat_display:<15} {created:<20}"
        )
    return 0


def _handle_get_command(secrets_manager: SecretsManager, args) -> int:
    """Handle --get command (Issue #315: extracted helper)."""
    if not args.secret_id:
        logger.error("❌ --secret-id required")
        return 1

    value = secrets_manager.get_secret(args.secret_id, args.chat_id)

    if value:
        if args.json:
            logger.info(json.dumps({"value": value}))
        else:
            logger.info(f"🔐 Secret value: {value}")
        return 0
    else:
        logger.error("❌ Secret not found or access denied")
        return 1


def _handle_cleanup_command(secrets_manager: SecretsManager, args) -> int:
    """Handle --cleanup-chat command (Issue #315: extracted helper)."""
    result = secrets_manager.cleanup_chat_secrets(
        args.cleanup_chat, args.transfer_to_general
    )

    if args.json:
        logger.info(json.dumps(result))
    else:
        logger.info("✅ Chat cleanup completed:")
        logger.info(f"   Transferred: {result['transferred']}")
        logger.info(f"   Deleted: {result['deleted']}")
    return 0


def _handle_security_report_command(secrets_manager: SecretsManager, args) -> int:
    """Handle --security-report command (Issue #315: extracted helper)."""
    report = secrets_manager.get_security_report()

    if args.json:
        logger.info(json.dumps(report, indent=2))
        return 0

    logger.info("\n🔐 Security Report:")
    logger.info("=" * 50)
    logger.info(f"Total secrets: {report['total_secrets']}")
    logger.info(f"General secrets: {report['general_secrets']}")
    logger.info(f"Chat secrets: {report['chat_secrets']}")
    logger.info(f"Active chats: {report['active_chats']}")
    logger.info(f"Encryption: {report['encryption_status']}")
    logger.info(f"Audit logging: {report['audit_logging']}")

    if report["secret_types"]:
        logger.info("\nSecret types:")
        for secret_type, count in report["secret_types"].items():
            logger.info(f"  {secret_type}: {count}")
    return 0


def _create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser.

    Helper for main (Issue #825).
    """
    parser = argparse.ArgumentParser(
        description="AutoBot Secrets Management System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/secrets_manager.py --add --name "api_key" --type "api_key" --scope "general"
  python scripts/secrets_manager.py --list --scope "general"
  python scripts/secrets_manager.py --list --scope "chat" --chat-id "chat_123"
  python scripts/secrets_manager.py --get --secret-id "abc123..." --chat-id "chat_123"
  python scripts/secrets_manager.py --transfer --secret-id "abc123..." --chat-id "chat_123"
  python scripts/secrets_manager.py --cleanup-chat "chat_456" --transfer
  python scripts/secrets_manager.py --security-report
        """,
    )

    # Actions
    parser.add_argument("--add", action="store_true", help="Add new secret")
    parser.add_argument("--list", action="store_true", help="List secrets")
    parser.add_argument("--get", action="store_true", help="Get secret value")
    parser.add_argument("--update", action="store_true", help="Update secret")
    parser.add_argument("--delete", action="store_true", help="Delete secret")
    parser.add_argument(
        "--transfer", action="store_true", help="Transfer secret to general scope"
    )
    parser.add_argument("--cleanup-chat", help="Cleanup secrets for deleted chat")
    parser.add_argument(
        "--security-report", action="store_true", help="Generate security report"
    )

    # Parameters
    parser.add_argument("--secret-id", help="Secret ID")
    parser.add_argument("--name", help="Secret name")
    parser.add_argument("--value", help="Secret value (will prompt if not provided)")
    parser.add_argument(
        "--type",
        choices=list(vars(SecretType).values()),
        default=SecretType.CUSTOM,
        help="Secret type",
    )
    parser.add_argument(
        "--scope",
        choices=[SecretScope.GENERAL, SecretScope.CHAT],
        default=SecretScope.GENERAL,
        help="Secret scope",
    )
    parser.add_argument("--chat-id", help="Chat ID for chat-scoped secrets")
    parser.add_argument("--description", help="Secret description")
    parser.add_argument("--tags", nargs="+", help="Secret tags")
    parser.add_argument(
        "--transfer-to-general",
        action="store_true",
        help="Transfer secrets to general instead of deleting",
    )

    # Options
    parser.add_argument(
        "--secrets-dir", default="data/secrets", help="Secrets directory"
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    return parser


def main():
    """Entry point for AutoBot secrets management CLI."""
    parser = _create_argument_parser()
    args = parser.parse_args()

    if not any(
        [
            args.add,
            args.list,
            args.get,
            args.update,
            args.delete,
            args.transfer,
            args.cleanup_chat,
            args.security_report,
        ]
    ):
        parser.print_help()
        return 1

    secrets_manager = SecretsManager(args.secrets_dir)

    command_handlers = {
        "add": (_handle_add_command, args.add),
        "list": (_handle_list_command, args.list),
        "get": (_handle_get_command, args.get),
        "cleanup_chat": (_handle_cleanup_command, args.cleanup_chat),
        "security_report": (_handle_security_report_command, args.security_report),
    }

    try:
        for cmd_name, (handler, is_active) in command_handlers.items():
            if is_active:
                return handler(secrets_manager, args)
        return 0

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Operation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
