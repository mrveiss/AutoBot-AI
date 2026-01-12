# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Secrets Management Service
Handles secure storage, retrieval, and management of secrets with dual-scope support
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from backend.type_defs.common import Metadata

from cryptography.fernet import Fernet

from src.config import config_manager

logger = logging.getLogger(__name__)


class SecretsService:
    """Service for managing secrets with encryption and scope isolation"""

    def __init__(self, db_path: str = None, encryption_key: Optional[str] = None):
        """Initialize the secrets service with encryption"""
        if db_path is None:
            # Use centralized path management for default path
            from backend.utils.paths_manager import ensure_data_directory, get_data_path

            ensure_data_directory()
            db_path = str(get_data_path("secrets.db"))

        self.db_path = db_path
        self._ensure_db_directory()

        # Initialize encryption
        self._init_encryption(encryption_key)

        # Initialize database
        self._init_database()

    def _ensure_db_directory(self):
        """Ensure the database directory exists"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    def _init_encryption(self, encryption_key: Optional[str] = None):
        """Initialize encryption with provided or generated key"""
        if encryption_key:
            self.cipher = Fernet(encryption_key.encode())
        else:
            # Generate a new key from config or environment
            env_key = config_manager.get("security.secrets_key", None)
            if env_key:
                self.cipher = Fernet(env_key.encode())
            else:
                # Generate and save a new key
                key = Fernet.generate_key()
                self.cipher = Fernet(key)
                logger.warning(
                    "Generated new encryption key. Set AUTOBOT_SECRETS_KEY environment variable for persistence."
                )

    def _init_database(self):
        """Initialize the SQLite database with secrets table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        self._create_secrets_table(cursor)
        self._create_secrets_indexes(cursor)
        self._create_audit_table(cursor)

        conn.commit()
        conn.close()

    def _create_secrets_table(self, cursor: sqlite3.Cursor):
        """Create the secrets table if it doesn't exist"""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS secrets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                secret_type TEXT NOT NULL,
                encrypted_value TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'general',
                chat_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                created_by TEXT,
                metadata TEXT,
                access_count INTEGER DEFAULT 0,
                last_accessed_at TEXT,
                is_active BOOLEAN DEFAULT 1,
                UNIQUE(name, scope, chat_id)
            )
        """
        )

    def _create_secrets_indexes(self, cursor: sqlite3.Cursor):
        """Create indexes for the secrets table"""
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_secrets_scope ON secrets(scope)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_secrets_chat_id ON secrets(chat_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_secrets_name ON secrets(name)"
        )

    def _create_audit_table(self, cursor: sqlite3.Cursor):
        """Create the audit log table if it doesn't exist"""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS secrets_audit (
                id TEXT PRIMARY KEY,
                secret_id TEXT NOT NULL,
                action TEXT NOT NULL,
                performed_by TEXT,
                performed_at TEXT NOT NULL,
                details TEXT,
                FOREIGN KEY (secret_id) REFERENCES secrets(id)
            )
        """
        )

    def _encrypt_value(self, value: str) -> str:
        """Encrypt a secret value"""
        return self.cipher.encrypt(value.encode()).decode()

    def _decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a secret value"""
        return self.cipher.decrypt(encrypted_value.encode()).decode()

    def _row_to_secret_dict(self, row: tuple, include_encrypted: bool = False) -> Dict:
        """Convert a database row to a secret dictionary"""
        secret = {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "secret_type": row[3],
            "scope": row[5],
            "chat_id": row[6],
            "created_at": row[7],
            "updated_at": row[8],
            "expires_at": row[9],
            "metadata": json.loads(row[10]) if row[10] else {},
            "access_count": row[11],
        }
        if include_encrypted:
            secret["_encrypted_value"] = row[4]
        return secret

    def _row_to_secret_list_item(self, row: tuple) -> Dict:
        """Convert a database row to a secret list item (without encrypted value)"""
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "secret_type": row[3],
            "scope": row[4],
            "chat_id": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "expires_at": row[8],
            "access_count": row[9],
        }

    def _is_secret_expired(self, expires_at: Optional[str]) -> bool:
        """Check if a secret has expired"""
        if not expires_at:
            return False
        return datetime.fromisoformat(expires_at) < datetime.now(timezone.utc)

    def _update_access_tracking(
        self, cursor: sqlite3.Cursor, secret_id: str, accessed_by: Optional[str]
    ):
        """Update access count and audit log for a secret"""
        cursor.execute(
            """
            UPDATE secrets
            SET access_count = access_count + 1,
                last_accessed_at = ?
            WHERE id = ?
        """,
            (datetime.now(timezone.utc).isoformat(), secret_id),
        )
        self._audit_action(cursor, secret_id, "accessed", accessed_by)

    def create_secret(
        self,
        name: str,
        secret_type: str,
        value: str,
        scope: str = "general",
        chat_id: Optional[str] = None,
        description: Optional[str] = None,
        expires_at: Optional[str] = None,
        metadata: Optional[Dict] = None,
        created_by: Optional[str] = None,
    ) -> Metadata:
        """Create a new secret with encryption"""
        secret_id = str(uuid4())
        encrypted_value = self._encrypt_value(value)
        now = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO secrets (
                    id, name, description, secret_type, encrypted_value,
                    scope, chat_id, created_at, updated_at, expires_at,
                    created_by, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    secret_id,
                    name,
                    description,
                    secret_type,
                    encrypted_value,
                    scope,
                    chat_id,
                    now,
                    now,
                    expires_at,
                    created_by,
                    json.dumps(metadata) if metadata else None,
                ),
            )

            # Add audit log entry
            self._audit_action(cursor, secret_id, "created", created_by)

            conn.commit()

            return {
                "id": secret_id,
                "name": name,
                "description": description,
                "secret_type": secret_type,
                "scope": scope,
                "chat_id": chat_id,
                "created_at": now,
                "expires_at": expires_at,
            }

        except sqlite3.IntegrityError:
            conn.rollback()
            raise ValueError(
                f"Secret with name '{name}' already exists in scope '{scope}' for chat '{chat_id}'"
            )
        finally:
            conn.close()

    def _build_get_secret_query(
        self,
        secret_id: Optional[str],
        name: Optional[str],
        scope: str,
        chat_id: Optional[str],
    ) -> tuple[Optional[str], List]:
        """Build query and params for get_secret. Returns (query, params) or (None, [])."""
        base_query = """
            SELECT id, name, description, secret_type, encrypted_value,
                   scope, chat_id, created_at, updated_at, expires_at,
                   metadata, access_count
            FROM secrets
            WHERE is_active = 1
        """
        params: List = []

        if secret_id:
            return base_query + " AND id = ?", [secret_id]
        elif name:
            query = base_query + " AND name = ? AND scope = ?"
            params = [name, scope]
            if scope == "chat" and chat_id:
                query += " AND chat_id = ?"
                params.append(chat_id)
            return query, params
        return None, []

    def get_secret(
        self,
        secret_id: Optional[str] = None,
        name: Optional[str] = None,
        scope: str = "general",
        chat_id: Optional[str] = None,
        include_value: bool = False,
        accessed_by: Optional[str] = None,
    ) -> Optional[Metadata]:
        """Get a secret by ID or name with optional value decryption"""
        query, params = self._build_get_secret_query(secret_id, name, scope, chat_id)
        if query is None:
            return None

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(query, params)
            row = cursor.fetchone()

            if not row:
                return None

            secret = self._row_to_secret_dict(row, include_encrypted=True)

            # Check expiration
            if self._is_secret_expired(secret["expires_at"]):
                return None

            # Handle value decryption and access tracking
            if include_value:
                secret["value"] = self._decrypt_value(secret.pop("_encrypted_value"))
                self._update_access_tracking(cursor, secret["id"], accessed_by)
                conn.commit()
            else:
                secret.pop("_encrypted_value", None)

            return secret
        finally:
            conn.close()

    def _build_list_secrets_query(
        self,
        scope: Optional[str],
        chat_id: Optional[str],
        secret_type: Optional[str],
        include_expired: bool,
    ) -> tuple[str, List]:
        """Build query and params for list_secrets."""
        query = """
            SELECT id, name, description, secret_type, scope, chat_id,
                   created_at, updated_at, expires_at, access_count
            FROM secrets
            WHERE is_active = 1
        """
        params: List = []

        if scope:
            query += " AND scope = ?"
            params.append(scope)
        if chat_id:
            query += " AND chat_id = ?"
            params.append(chat_id)
        if secret_type:
            query += " AND secret_type = ?"
            params.append(secret_type)
        if not include_expired:
            query += " AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))"

        return query + " ORDER BY created_at DESC", params

    def list_secrets(
        self,
        scope: Optional[str] = None,
        chat_id: Optional[str] = None,
        secret_type: Optional[str] = None,
        include_expired: bool = False,
    ) -> List[Metadata]:
        """List secrets based on filters"""
        query, params = self._build_list_secrets_query(
            scope, chat_id, secret_type, include_expired
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(query, params)
            return [self._row_to_secret_list_item(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _build_update_params(
        self,
        name: Optional[str],
        description: Optional[str],
        value: Optional[str],
        expires_at: Optional[str],
        metadata: Optional[Dict],
    ) -> tuple[List[str], List]:
        """Build update clauses and params for update_secret."""
        updates: List[str] = []
        params: List = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if value is not None:
            updates.append("encrypted_value = ?")
            params.append(self._encrypt_value(value))
        if expires_at is not None:
            updates.append("expires_at = ?")
            params.append(expires_at)
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        return updates, params

    def update_secret(
        self,
        secret_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        value: Optional[str] = None,
        expires_at: Optional[str] = None,
        metadata: Optional[Dict] = None,
        updated_by: Optional[str] = None,
    ) -> bool:
        """Update an existing secret"""
        updates, params = self._build_update_params(
            name, description, value, expires_at, metadata
        )
        if not updates:
            return False

        # Add timestamp and secret_id
        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(secret_id)

        query = f"UPDATE secrets SET {', '.join(updates)} WHERE id = ? AND is_active = 1"

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(query, params)
            if cursor.rowcount > 0:
                self._audit_action(cursor, secret_id, "updated", updated_by)
                conn.commit()
                return True
            return False
        finally:
            conn.close()

    def delete_secret(
        self,
        secret_id: str,
        hard_delete: bool = False,
        deleted_by: Optional[str] = None,
    ) -> bool:
        """Delete or deactivate a secret"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if hard_delete:
            cursor.execute("DELETE FROM secrets WHERE id = ?", (secret_id,))
            action = "deleted"
        else:
            cursor.execute(
                "UPDATE secrets SET is_active = 0, updated_at = ? WHERE id = ? AND is_active = 1",
                (datetime.now(timezone.utc).isoformat(), secret_id),
            ),
            action = "deactivated"

        if cursor.rowcount > 0:
            self._audit_action(cursor, secret_id, action, deleted_by)
            conn.commit()
            conn.close()
            return True

        conn.close()
        return False

    def transfer_secret(
        self,
        secret_id: str,
        from_scope: str,
        to_scope: str,
        target_chat_id: Optional[str] = None,
        transferred_by: Optional[str] = None,
    ) -> bool:
        """Transfer a secret between scopes"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Verify secret exists and matches from_scope
        cursor.execute(
            "SELECT scope FROM secrets WHERE id = ? AND is_active = 1", (secret_id,)
        ),
        row = cursor.fetchone()

        if not row or row[0] != from_scope:
            conn.close()
            return False

        # Update scope and chat_id
        cursor.execute(
            "UPDATE secrets SET scope = ?, chat_id = ?, updated_at = ? WHERE id = ?",
            (
                to_scope,
                target_chat_id,
                datetime.now(timezone.utc).isoformat(),
                secret_id,
            ),
        )

        if cursor.rowcount > 0:
            details = {
                "from_scope": from_scope,
                "to_scope": to_scope,
                "target_chat_id": target_chat_id,
            }
            self._audit_action(
                cursor, secret_id, "transferred", transferred_by, details
            )
            conn.commit()
            conn.close()
            return True

        conn.close()
        return False

    def cleanup_chat_secrets(
        self,
        chat_id: str,
        action: str = "delete",  # "delete", "transfer", "export"
        target_chat_id: Optional[str] = None,
        cleaned_by: Optional[str] = None,
    ) -> Metadata:
        """Clean up secrets when a chat is deleted"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all secrets for the chat
        cursor.execute(
            "SELECT id, name FROM secrets WHERE chat_id = ? AND is_active = 1",
            (chat_id,),
        ),
        chat_secrets = cursor.fetchall()

        results = {
            "action": action,
            "chat_id": chat_id,
            "affected_secrets": len(chat_secrets),
            "secrets": [],
        }

        for secret_id, name in chat_secrets:
            if action == "delete":
                self.delete_secret(secret_id, deleted_by=cleaned_by)
                results["secrets"].append(
                    {"id": secret_id, "name": name, "status": "deleted"}
                )

            elif action == "transfer" and target_chat_id:
                success = self.transfer_secret(
                    secret_id, "chat", "chat", target_chat_id, cleaned_by
                )
                results["secrets"].append(
                    {
                        "id": secret_id,
                        "name": name,
                        "status": "transferred" if success else "failed",
                    }
                )

            elif action == "export":
                # Export logic would go here
                results["secrets"].append(
                    {"id": secret_id, "name": name, "status": "exported"}
                )

        conn.close()
        return results

    def _audit_action(
        self,
        cursor: sqlite3.Cursor,
        secret_id: str,
        action: str,
        performed_by: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        """Add an audit log entry"""
        cursor.execute(
            """
            INSERT INTO secrets_audit (id, secret_id, action, performed_by, performed_at, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                str(uuid4()),
                secret_id,
                action,
                performed_by,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(details) if details else None,
            ),
        )

    def get_audit_log(
        self, secret_id: Optional[str] = None, limit: int = 100
    ) -> List[Metadata]:
        """Get audit log entries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if secret_id:
            cursor.execute(
                "SELECT * FROM secrets_audit WHERE secret_id = ? ORDER BY performed_at DESC LIMIT ?",
                (secret_id, limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM secrets_audit ORDER BY performed_at DESC LIMIT ?",
                (limit,),
            )

        audit_entries = []
        for row in cursor.fetchall():
            audit_entries.append(
                {
                    "id": row[0],
                    "secret_id": row[1],
                    "action": row[2],
                    "performed_by": row[3],
                    "performed_at": row[4],
                    "details": json.loads(row[5]) if row[5] else {},
                }
            )

        conn.close()
        return audit_entries


# Singleton instance getter (thread-safe)
import threading

_secrets_service = None
_secrets_service_lock = threading.Lock()


def get_secrets_service() -> SecretsService:
    """Get or create the secrets service singleton (thread-safe)."""
    global _secrets_service
    if _secrets_service is None:
        with _secrets_service_lock:
            # Double-check after acquiring lock
            if _secrets_service is None:
                _secrets_service = SecretsService()
    return _secrets_service
